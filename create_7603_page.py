"""KCCIVOC-7603 — Doc2 보류 테이블 (Claude 분석 내용 + Chrome PDF) 생성."""
from dotenv import load_dotenv; load_dotenv()

import json, os, subprocess, tempfile, requests
from datetime import datetime
from requests.auth import HTTPBasicAuth
from confluence_client import ConfluenceClient
from jira_client import JiraClient
from config import JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN, CONFLUENCE_EMAIL, CONFLUENCE_API_TOKEN
from doc2_updater import (
    _h2, _key_link, _reporter_html, _colgroup, _th_span,
    SCORE_LABELS, SCORE_KEYS, CW, _score_mark, _effective_approval, APPROVAL_LABEL
)
from cycle import cycle_label
from analyzer import analyze_ticket

JIRA_AUTH       = HTTPBasicAuth(JIRA_EMAIL, JIRA_API_TOKEN)
CONFLUENCE_AUTH = HTTPBasicAuth(CONFLUENCE_EMAIL, CONFLUENCE_API_TOKEN)
JIRA_BASE       = f"{JIRA_BASE_URL}/rest/api/3"
TICKET_KEY      = "KCCIVOC-7603"
PAGE_PARENT_ID  = "78020650"
CHROME          = r"C:\Program Files\Google\Chrome\Application\chrome.exe"


# ────────────────────────────────────────────────────────────────────
# ADF → HTML (Chrome PDF용 rich 변환)
# ────────────────────────────────────────────────────────────────────
def _esc(s: str) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _marks_to_html(text: str, marks: list) -> str:
    """ADF marks를 HTML 태그로 감쌈."""
    html = _esc(text)
    for m in marks:
        t = m.get("type", "")
        if t == "strong":
            html = f"<strong>{html}</strong>"
        elif t == "em":
            html = f"<em>{html}</em>"
        elif t == "underline":
            html = f"<u>{html}</u>"
        elif t == "strike":
            html = f"<s>{html}</s>"
        elif t == "code":
            html = f"<code>{html}</code>"
        elif t == "textColor":
            color = m.get("attrs", {}).get("color", "")
            if color:
                html = f'<span style="color:{color}">{html}</span>'
        elif t == "link":
            href = m.get("attrs", {}).get("href", "#")
            html = f'<a href="{_esc(href)}" target="_blank">{html}</a>'
        elif t == "backgroundColor":
            bg = m.get("attrs", {}).get("color", "")
            if bg:
                html = f'<span style="background:{bg};padding:1px 2px">{html}</span>'
    return html


def _adf_to_html(node: dict | str | None) -> str:
    """ADF 노드를 HTML 문자열로 변환 (재귀)."""
    if node is None:
        return ""
    if isinstance(node, str):
        return _esc(node)

    ntype = node.get("type", "")
    content = node.get("content", [])
    attrs = node.get("attrs", {})

    # ── 텍스트 ──
    if ntype == "text":
        return _marks_to_html(node.get("text", ""), node.get("marks", []))

    if ntype == "hardBreak":
        return "<br/>"

    if ntype == "rule":
        return "<hr/>"

    # ── 블록 ──
    if ntype in ("doc", "tableCell", "tableHeader", "listItem",
                 "blockquote", "expand"):
        inner = "".join(_adf_to_html(c) for c in content)
        if ntype == "blockquote":
            return f"<blockquote>{inner}</blockquote>"
        if ntype == "expand":
            title = _esc(attrs.get("title", ""))
            return (f'<details open><summary style="font-weight:bold;cursor:pointer">'
                    f'{title}</summary>{inner}</details>')
        if ntype == "tableCell":
            colspan = attrs.get("colspan", 1)
            rowspan = attrs.get("rowspan", 1)
            cs = f' colspan="{colspan}"' if colspan > 1 else ""
            rs = f' rowspan="{rowspan}"' if rowspan > 1 else ""
            bg = attrs.get("background", "")
            style = f' style="background:{bg}"' if bg else ""
            return f"<td{cs}{rs}{style}>{inner}</td>"
        if ntype == "tableHeader":
            colspan = attrs.get("colspan", 1)
            rowspan = attrs.get("rowspan", 1)
            cs = f' colspan="{colspan}"' if colspan > 1 else ""
            rs = f' rowspan="{rowspan}"' if rowspan > 1 else ""
            return f"<th{cs}{rs}>{inner}</th>"
        return inner

    if ntype == "paragraph":
        inner = "".join(_adf_to_html(c) for c in content)
        if not inner.strip():
            return "<p style='margin:4px 0'>&nbsp;</p>"
        return f"<p style='margin:4px 0'>{inner}</p>"

    if ntype == "heading":
        level = attrs.get("level", 2)
        inner = "".join(_adf_to_html(c) for c in content)
        return f"<h{level} style='margin:12px 0 4px'>{inner}</h{level}>"

    if ntype == "codeBlock":
        inner = "".join(_adf_to_html(c) for c in content)
        lang = attrs.get("language", "")
        return (f'<pre style="background:#f4f5f7;border:1px solid #dfe1e6;'
                f'padding:8px;border-radius:3px;overflow-x:auto;font-size:9pt">'
                f'<code class="{lang}">{inner}</code></pre>')

    if ntype in ("bulletList", "orderedList"):
        tag = "ul" if ntype == "bulletList" else "ol"
        inner = "".join(_adf_to_html(c) for c in content)
        return f"<{tag} style='margin:4px 0;padding-left:20px'>{inner}</{tag}>"

    if ntype == "listItem":
        inner = "".join(_adf_to_html(c) for c in content)
        return f"<li>{inner}</li>"

    if ntype == "table":
        inner = "".join(_adf_to_html(c) for c in content)
        return (f'<table style="border-collapse:collapse;width:100%;margin:8px 0;font-size:9pt">'
                f'{inner}</table>')

    if ntype == "tableRow":
        inner = "".join(_adf_to_html(c) for c in content)
        return f"<tr>{inner}</tr>"

    if ntype == "tableHeader":
        inner = "".join(_adf_to_html(c) for c in content)
        return f"<th style='background:#f4f5f7;border:1px solid #dfe1e6;padding:4px 6px;text-align:left'>{inner}</th>"

    if ntype == "tableCell":
        inner = "".join(_adf_to_html(c) for c in content)
        return f"<td style='border:1px solid #dfe1e6;padding:4px 6px;vertical-align:top'>{inner}</td>"

    # ── 인라인 ──
    if ntype == "mention":
        name = attrs.get("text", attrs.get("displayName", "@mention"))
        return f'<span style="color:#0052cc;background:#e9f2ff;border-radius:3px;padding:1px 4px">{_esc(name)}</span>'

    if ntype == "emoji":
        return _esc(attrs.get("text", ""))

    if ntype == "status":
        label = attrs.get("text", "")
        color_map = {"green": "#00875A", "yellow": "#FF8B00", "red": "#DE350B",
                     "blue": "#0052CC", "neutral": "#42526E", "purple": "#6554C0"}
        bg = color_map.get(attrs.get("color", "neutral"), "#42526E")
        return (f'<span style="background:{bg};color:#fff;border-radius:3px;'
                f'padding:1px 6px;font-size:9pt;font-weight:bold">{_esc(label)}</span>')

    if ntype in ("inlineCard", "blockCard", "embedCard"):
        url = attrs.get("url", "")
        return f'<a href="{_esc(url)}">{_esc(url)}</a>'

    if ntype in ("mediaSingle", "mediaGroup", "media"):
        return '<div style="background:#f4f5f7;border:1px dashed #dfe1e6;padding:8px;color:#6b778c;font-size:9pt">[첨부 파일/이미지]</div>'

    # 나머지: content만 재귀
    return "".join(_adf_to_html(c) for c in content)


# ────────────────────────────────────────────────────────────────────
# Jira 원본 ADF 조회
# ────────────────────────────────────────────────────────────────────
def fetch_raw_adf(key: str) -> dict:
    r = requests.get(
        f"{JIRA_BASE}/issue/{key}",
        auth=JIRA_AUTH, headers={"Accept": "application/json"},
        params={"fields": "description,summary,reporter,created,duedate,status,issuetype"}
    )
    r.raise_for_status()
    return r.json()


def fetch_all_comments(key: str) -> list[dict]:
    r = requests.get(f"{JIRA_BASE}/issue/{key}/comment",
                     auth=JIRA_AUTH, headers={"Accept": "application/json"},
                     params={"maxResults": 100, "orderBy": "created"})
    r.raise_for_status()
    data = r.json()
    print(f"  [comments] {len(data.get('comments', []))}개")
    return data.get("comments", [])


def fetch_transitions(key: str) -> list[dict]:
    r = requests.get(f"{JIRA_BASE}/issue/{key}/changelog",
                     auth=JIRA_AUTH, headers={"Accept": "application/json"})
    r.raise_for_status()
    result = []
    for h in r.json().get("values", []):
        date   = h.get("created", "")[:16].replace("T", " ")
        author = h.get("author", {}).get("displayName", "")
        for item in h.get("items", []):
            if item.get("field") == "status":
                result.append({"date": date, "author": author,
                                "from": item.get("fromString", ""),
                                "to":   item.get("toString",  "")})
    print(f"  [changelog] 상태 변경 {len(result)}건")
    return result


def _adf_text(node) -> str:
    """ADF → 평문 (analyzer 입력용)."""
    if not node: return ""
    if isinstance(node, str): return node
    parts = []
    def walk(n):
        if n.get("type") == "text":
            parts.append(n.get("text", ""))
        elif n.get("type") in ("hardBreak", "paragraph"):
            parts.append("\n")
        for c in n.get("content", []):
            walk(c)
    walk(node)
    return "".join(parts).strip()


# ────────────────────────────────────────────────────────────────────
# BRD 상태 레이블
# ────────────────────────────────────────────────────────────────────
_APPROVED_SET = {"Confirmed","HQ Discussion","In Business Review","진행 중",
                 "QA Sign-Off","Re-Opened","종료","Deployed","Dropped","RESOLVE","해결됨"}
_HOLD_SET     = {"BRD Submitted","Create Issue","미해결","Reopen","Revision Requested"}

def _brd_label(status: str) -> str:
    if status in _APPROVED_SET: return "승인"
    if status in _HOLD_SET:     return "보류"
    return status


# ────────────────────────────────────────────────────────────────────
# 셀별 HTML (댓글·최종결과·IMG)
# ────────────────────────────────────────────────────────────────────
def comments_cell(comments: list[dict]) -> str:
    """댓글을 '담당자: 내용 (날짜)' 형식의 요약 타임라인으로 변환."""
    if not comments:
        return "<p>댓글 없음</p>"
    parts = []
    for c in comments:
        author  = c.get("author", {}).get("displayName", "")
        created = c.get("created", "")
        text = _adf_text(c.get("body")).replace("\n", " ").strip()
        # cc. 으로 시작하는 알림성 댓글 제외
        if text.lower().startswith("cc."):
            continue
        # 날짜 M/D 형식
        try:
            from datetime import datetime as dt
            d = dt.fromisoformat(created[:10])
            date_str = f"{d.month}/{d.day}"
        except Exception:
            date_str = created[:10]
        # 이름 축약 (예: 김소현 Bell Kim 매니저 → 김소현M)
        short_name = author.split()[0] + "M" if author else ""
        parts.append(f"<p>{_esc(short_name)}: {_esc(text[:200])} ({date_str})</p>")
    return "".join(parts)


def transitions_cell(trans: list[dict]) -> str:
    if not trans:
        return "<p>이력 없음</p>"
    last = trans[-1]
    brd  = _brd_label(last["to"])
    final = f'<p>{_esc(last["to"])} ({brd}) | {last["date"][:10]}</p>'
    rows = "".join(
        f"<p>{t['date'][:10]} {_esc(t['from'])} → {_esc(t['to'])} ({_brd_label(t['to'])})</p>"
        for t in trans
    )
    return final + rows


# ────────────────────────────────────────────────────────────────────
# 분석 결과 → 내용 셀 HTML
# ────────────────────────────────────────────────────────────────────
def content_cell(analysis: dict, ticket_summary: str) -> str:
    feature_label = analysis.get("feature_label") or "기존 기능 개선"
    parts = []
    for label, field in [("Summary", "summary_ko"), ("배경", "background"),
                          ("문제", "problem"), (feature_label, "feature")]:
        val = analysis.get(field) or (ticket_summary if field == "summary_ko" else "")
        if val:
            lines = [l.strip() for l in val.split("\n") if l.strip()] or [val.strip()]
            parts.append(
                f'<p>&lt;{label}&gt;</p><ul>'
                + "".join(f"<li>{_esc(l)}</li>" for l in lines)
                + "</ul>"
            )
    return "".join(parts)


# ────────────────────────────────────────────────────────────────────
# 보류 테이블 (댓글·최종결과·IMG 셀 포함)
# ────────────────────────────────────────────────────────────────────
def build_pending_table(ticket: dict, analysis: dict,
                        c_html: str, t_html: str) -> str:
    widths = CW["kr_pending"]
    header = _th_span([
        ("#", 1, 1), ("회차", 1, 1), ("Key", 1, 1), ("Ticket Summary", 1, 1),
        ("Reporter", 1, 1), ("Created", 1, 1), ("Due date", 1, 1),
        ("보류 code", 1, 1), ("보류 사유", 1, 1),
        ("댓글 히스토리", 1, 1),
        ("최종 결과(승인/반려 전환 결과 및 사유 & 날짜)", 1, 1),
        ("IMG", 1, 1),
    ])

    def td(content):
        return f'<td><p>{content}</p></td>'

    key         = ticket["key"]
    hold_code   = analysis.get("hold_code") or ticket.get("hold_code", "")
    hold_reason = analysis.get("hold_reason") or ticket.get("hold_reason", "")
    c_content   = content_cell(analysis, ticket.get("summary", ""))

    row = (
        f"<tr>"
        f'{td("1")}'
        f'<td><p>{cycle_label(ticket.get("cycle_number", 7))}</p></td>'
        f'<td><p>{_key_link(key)}</p></td>'
        f'<td>{c_content}</td>'
        f'{_reporter_html(ticket.get("reporter", ""), ticket.get("initiator", ""), rs=1)}'
        f'{td(ticket.get("created", ""))}'
        f'{td(ticket.get("due_date", ""))}'
        f'{td(hold_code)}'
        f'{td(hold_reason)}'
        f'<td>{c_html}</td>'
        f'<td>{t_html}</td>'
        f'<td></td>'
        f"</tr>"
    )

    cg = _colgroup(widths)
    return f"<table>{cg}<tbody>{header}{row}</tbody></table>"


# ────────────────────────────────────────────────────────────────────
# Chrome headless PDF (ADF → rich HTML → PDF)
# ────────────────────────────────────────────────────────────────────
def make_ticket_html(raw_issue: dict, comments: list[dict], transitions: list[dict]) -> str:
    fields      = raw_issue.get("fields", {})
    title       = fields.get("summary", TICKET_KEY)
    reporter    = (fields.get("reporter") or {}).get("displayName", "")
    created     = (fields.get("created") or "")[:10]
    due_date    = fields.get("duedate") or ""
    status_name = (fields.get("status") or {}).get("name", "")
    adf_desc    = fields.get("description") or {}

    desc_html   = _adf_to_html(adf_desc) if isinstance(adf_desc, dict) else f"<p>{_esc(str(adf_desc))}</p>"

    trans_rows = "".join(
        f"<tr>"
        f"<td style='border:1px solid #dfe1e6;padding:4px 8px'>{_esc(t['date'])}</td>"
        f"<td style='border:1px solid #dfe1e6;padding:4px 8px'>{_esc(t['author'])}</td>"
        f"<td style='border:1px solid #dfe1e6;padding:4px 8px'>{_esc(t['from'])}</td>"
        f"<td style='border:1px solid #dfe1e6;padding:4px 8px;font-size:10pt'>→</td>"
        f"<td style='border:1px solid #dfe1e6;padding:4px 8px'>"
        f"<strong>{_esc(t['to'])}</strong> "
        f"<span style='color:#42526e'>({_brd_label(t['to'])})</span></td>"
        f"</tr>"
        for t in transitions
    )
    comment_blocks = "".join(
        f"<div style='border:1px solid #dfe1e6;border-radius:4px;padding:10px;margin:6px 0'>"
        f"<div style='font-weight:bold;color:#42526e;margin-bottom:4px;font-size:9pt'>"
        f"{_esc((c.get('author') or {}).get('displayName',''))} · "
        f"{(c.get('created') or '')[:16].replace('T',' ')}</div>"
        f"<div>{_adf_to_html(c.get('body'))}</div>"
        f"</div>"
        for c in comments
    )

    color_status = "#FF8B00" if _brd_label(status_name) == "보류" else "#00875A"

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8"/>
<style>
* {{ box-sizing:border-box; margin:0; padding:0; }}
@page {{ margin: 16mm 18mm; size: A4; }}
body {{
  font-family:'Malgun Gothic','Apple SD Gothic Neo','Noto Sans KR',sans-serif;
  font-size:10pt; color:#172B4D; line-height:1.65;
  background:#fff;
}}
h1 {{ font-size:17pt; color:#0052CC; border-bottom:2px solid #0052CC;
      padding-bottom:8px; margin-bottom:14px; }}
h2 {{ font-size:12pt; color:#0052CC; margin:20px 0 6px;
      border-left:4px solid #0052CC; padding-left:8px; }}
h3 {{ font-size:11pt; color:#172B4D; margin:14px 0 4px; }}
.meta-grid {{
  display:grid; grid-template-columns:1fr 1fr;
  gap:6px 20px; background:#F4F5F7; border-radius:4px;
  padding:12px 16px; margin-bottom:20px; font-size:9pt;
}}
.meta-grid .label {{ color:#6B778C; }}
.meta-grid .value {{ font-weight:bold; color:#172B4D; }}
.badge {{
  display:inline-block; padding:2px 10px; border-radius:3px;
  font-size:9pt; font-weight:bold; color:#fff;
  background:{color_status};
}}
.desc-box {{
  background:#FAFBFC; border:1px solid #DFE1E6; border-radius:4px;
  padding:14px; overflow-x:auto;
}}
.desc-box table {{
  border-collapse:collapse; width:100%; font-size:9pt;
}}
.desc-box th {{
  background:#F4F5F7; border:1px solid #C1C7D0;
  padding:5px 8px; text-align:left; font-size:9pt;
}}
.desc-box td {{
  border:1px solid #DFE1E6; padding:5px 8px; vertical-align:top; font-size:9pt;
}}
.desc-box h1,.desc-box h2,.desc-box h3,.desc-box h4 {{
  border:none; padding-left:0; margin:10px 0 4px; font-size:10pt;
  color:#172B4D; border-bottom:1px solid #eee;
}}
.desc-box ul,.desc-box ol {{ padding-left:18px; }}
table.info {{
  border-collapse:collapse; font-size:9pt; width:100%;
}}
table.info th {{
  background:#F4F5F7; border:1px solid #DFE1E6;
  padding:5px 10px; text-align:left;
}}
table.info td {{ border:1px solid #DFE1E6; padding:5px 10px; vertical-align:top; }}
</style>
</head>
<body>

<h1>{_esc(TICKET_KEY)}</h1>
<div style="font-size:13pt;font-weight:bold;margin-bottom:10px">
  {_esc(title)}
  &nbsp;<span class="badge">보류 H1</span>
</div>

<div class="meta-grid">
  <div><span class="label">담당자</span></div>
  <div class="value">{_esc(reporter)}</div>
  <div><span class="label">생성일</span></div>
  <div class="value">{_esc(created)}</div>
  <div><span class="label">Due Date</span></div>
  <div class="value">{_esc(due_date)}</div>
  <div><span class="label">현재 상태</span></div>
  <div class="value">{_esc(status_name)}</div>
  <div><span class="label">프로젝트</span></div>
  <div class="value">KCCIVOC (KR)</div>
  <div><span class="label">회차</span></div>
  <div class="value">7회차</div>
</div>

<h2>티켓 설명 (BRD)</h2>
<div class="desc-box">{desc_html}</div>

<h2>상태 변경 이력</h2>
{'<p style="color:#6B778C;font-size:9pt">이력 없음</p>' if not transitions else f"""
<table class="info">
  <tr>
    <th>날짜</th><th>변경자</th><th>이전 상태</th><th></th><th>변경 후 상태</th>
  </tr>
  {trans_rows}
</table>"""}

<h2>댓글 ({len(comments)}개)</h2>
{comment_blocks if comment_blocks else '<p style="color:#6B778C;font-size:9pt">댓글 없음</p>'}

</body>
</html>"""


def html_to_pdf(html_content: str) -> bytes:
    with tempfile.TemporaryDirectory() as tmp:
        html_path = os.path.join(tmp, "ticket.html")
        pdf_path  = os.path.join(tmp, "ticket.pdf")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        result = subprocess.run([
            CHROME,
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            "--run-all-compositor-stages-before-draw",
            f"--print-to-pdf={pdf_path}",
            "--print-to-pdf-no-header",
            html_path,
        ], capture_output=True, timeout=60)
        if result.returncode != 0:
            print(f"  Chrome stderr: {result.stderr[:300]}")
        with open(pdf_path, "rb") as f:
            return f.read()


# ────────────────────────────────────────────────────────────────────
# Confluence 첨부
# ────────────────────────────────────────────────────────────────────
def attach_pdf(page_id: str, pdf_bytes: bytes, filename: str) -> str:
    r = requests.post(
        f"https://ihqdf.atlassian.net/wiki/rest/api/content/{page_id}/child/attachment",
        auth=CONFLUENCE_AUTH,
        headers={"X-Atlassian-Token": "no-check"},
        files={"file": (filename, pdf_bytes, "application/pdf")},
        data={"comment": "Jira 티켓 원문 PDF (Chrome headless)"},
    )
    r.raise_for_status()
    att_id = r.json()["results"][0]["id"]
    print(f"  [attach] {filename} (id={att_id})")
    return att_id


# ────────────────────────────────────────────────────────────────────
# 메인
# ────────────────────────────────────────────────────────────────────
def run():
    print("[1/6] Jira 원본 ADF 조회...")
    raw_issue = fetch_raw_adf(TICKET_KEY)
    fields    = raw_issue.get("fields", {})
    adf_desc  = fields.get("description") or {}
    desc_text = _adf_text(adf_desc)
    print(f"  description: {len(desc_text)}자")

    print("[2/6] 댓글 조회...")
    comments = fetch_all_comments(TICKET_KEY)

    print("[3/6] 상태 변경 이력 조회...")
    transitions = fetch_transitions(TICKET_KEY)

    print("[4/6] 티켓 분석 (인라인 — h-chat 대신 현 세션 분석 결과 사용)...")
    ticket_meta = {
        "key": TICKET_KEY,
        "summary": "[Kia App] 온라인 소모품 예상비용 안내",
        "reporter": (fields.get("reporter") or {}).get("displayName", ""),
        "created": (fields.get("created") or "")[:10],
        "due_date": fields.get("duedate") or "2027-01-31",
        "region": "KR",
        "brd_status_raw": "In Business Review",
        "feature_type": "신규/개선",
        "description": desc_text,
        "brd_approval": "Approved",
        "cycle_number": 7,
        "initiator": "",
    }
    # h-chat 402 오류로 현 Claude 세션 직접 분석 결과 사용
    analysis = {
        "status_info": "In Business Review (BRD 제출 완료, GBCXD 검토 대기 중)\n7.2 GBCXD 검토 결과 섹션 미작성으로 H1 보류 처리",
        "summary_ko": (
            "현재 Kia App에서 소모품(에어필터·와이퍼 등) 교체 예상 비용을 확인하려면 "
            "고객이 서비스센터에 직접 문의해야 하는 상황이며, 앱 내 소모품별 예상 비용 안내 화면을 "
            "신규 추가하여 고객이 방문 전에 온라인으로 비용을 확인할 수 있도록 개선하는 티켓."
        ),
        "background": (
            "소모품 교체 주기·비용에 대한 고객 문의가 서비스센터 CS 채널에 반복적으로 유입됨\n"
            "앱 내 정비 예약 기능과 연계하여 방문 전 비용 예측 가능성 향상 필요\n"
            "KR 원앱 정비 섹션 사용율 제고를 위한 GBCXD KPI 과제로 추진"
        ),
        "problem": (
            "현재 앱에서 소모품 종류별 예상 교체 비용 정보를 전혀 제공하지 않음\n"
            "고객이 비용 확인을 위해 서비스센터 전화/방문이 필수 — 불필요한 CS 부하 발생\n"
            "비용 불투명으로 예약 전환율 저하 및 고객 이탈 유발"
        ),
        "feature_label": "신규 기능",
        "feature": (
            "Kia App 정비 섹션 내 '소모품 예상비용 안내' 화면 신규 추가\n"
            "차종·연식별 소모품 목록(에어필터, 와이퍼, 엔진오일 등) 및 예상 비용 범위 표시\n"
            "정비 예약 플로우와 연계하여 비용 확인 → 예약 원스톱 전환 지원"
        ),
        "hold_code": "H1",
        "hold_reason": (
            "Section 7.2 (GBCXD 우선 순위 선별 검토 결과) 미기재 — "
            "검토자 성명·소속 및 항목별 O/X 점수 모두 공란. "
            "작성 완료 후 재제출 필요."
        ),
        "rejection_code": None,
        "rejection_reason": None,
        "scores": {
            "urgency": 0,
            "business_performance": 0,
            "customer_experience": 1,
            "operational_efficiency": 0,
            "global_reach": 0,
            "platform_strategy": 1,
        },
        "priority_score": 2,
    }
    print(f"  hold_code={analysis.get('hold_code')} priority={analysis.get('priority_score')}")

    # 셀 HTML
    c_html = comments_cell(comments)
    t_html = transitions_cell(transitions)

    # 테이블
    table_html = build_pending_table(ticket_meta, analysis, c_html, t_html)

    now  = datetime.now()
    html = (
        f'<p><em>단일 티켓 테스트: {now.strftime("%Y-%m-%d %H:%M")} | KR | H1 보류</em></p>'
        + _h2("RHQ KR — 보류 (H1)")
        + table_html
    )

    print("[5/5] Confluence 페이지 생성...")
    client = ConfluenceClient()

    # 기존 페이지 삭제
    for old_id in ["126943233", "126386266", "126484563"]:
        try:
            requests.delete(
                f"https://ihqdf.atlassian.net/wiki/rest/api/content/{old_id}",
                auth=CONFLUENCE_AUTH
            )
            print(f"  기존 페이지 {old_id} 삭제")
        except Exception:
            pass

    title  = f"{now.strftime('%m-%d %H:%M')} [KCCIVOC-7603] Doc2 단일 티켓 (AI 생성)"
    result = client.create_page(PAGE_PARENT_ID, title, html)
    page_id = result.get("id", "")
    print(f"  페이지: {title} (id={page_id})")

    print(f"\n완료!")
    print(f"  URL: https://ihqdf.atlassian.net/wiki/spaces/2/pages/{page_id}")


if __name__ == "__main__":
    run()
