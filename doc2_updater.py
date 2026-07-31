"""
Document 2: 신규/개선 전체 현황 업데이트

Confluence 페이지에 아래 마커가 미리 삽입되어 있어야 합니다:
  <!-- AUTO_SUMMARY_START --> ... <!-- AUTO_SUMMARY_END -->
  <!-- AUTO_TABLE_START --> ... <!-- AUTO_TABLE_END -->
  <!-- AUTO_PENDING_START --> ... <!-- AUTO_PENDING_END -->
  <!-- AUTO_HISTORY_START --> ... <!-- AUTO_HISTORY_END -->  ← 누적 추가(Append)
"""
from confluence_client import ConfluenceClient
from cycle import cycle_label

REGIONS = ["RHQ KR", "RHQ EU", "HQ GBCXD 및 타부문"]
REGION_MAP = {"KR": "RHQ KR", "EU": "RHQ EU", "HQ": "HQ GBCXD 및 타부문"}
SCORE_LABELS = {
    "urgency":                "시급성",
    "business_performance":   "사업 성과 기여",
    "customer_experience":    "고객 경험 영향도",
    "operational_efficiency": "운영 효율화",
    "global_reach":           "글로벌 파급 범위",
    "platform_strategy":      "플랫폼 운영 전략 연계도",
}


def _cnt(tickets, region=None, approval=None):
    result = tickets
    if region:
        result = [t for t in result if REGION_MAP.get(t.get("region")) == region]
    if approval:
        if isinstance(approval, list):
            result = [t for t in result if t.get("brd_approval") in approval]
        else:
            result = [t for t in result if t.get("brd_approval") == approval]
    return len(result)


def _th(*headers) -> str:
    return "<tr>" + "".join(f"<th><p>{h}</p></th>" for h in headers) + "</tr>"

def _td(*cells) -> str:
    return "<tr>" + "".join(f"<td><p>{c}</p></td>" for c in cells) + "</tr>"


# ── 결과 1: 종합 현황 ──────────────────────────────────────
def _build_summary_html(tickets: list[dict]) -> str:
    rows = [_th("구분", "티켓 인입 수", "승인", "반려", "보류")]
    for label, region in [("Total", None), ("RHQ KR", "RHQ KR"),
                           ("RHQ EU", "RHQ EU"), ("HQ GBCXD 및 타부문", "HQ GBCXD 및 타부문")]:
        rows.append(_td(
            label,
            str(_cnt(tickets, region)),
            str(_cnt(tickets, region, "Approved")),
            str(_cnt(tickets, region, "Rejected")),
            str(_cnt(tickets, region, ["Pending", "Pre-BRD"])),
        ))
    return f"<table><tbody>{''.join(rows)}</tbody></table>"


# ── 결과 2: 상세 티켓 테이블 (기본 + 분석) ───────────────────
def _build_table_html(tickets: list[dict]) -> str:
    rows = [_th("회차", "Key", "Ticket Summary", "Reporter", "Created", "Due Date",
                "내용", "항목별 분포", "Priority 점수", "BRD 승인 여부")]
    for t in tickets:
        scores = t.get("scores", {})
        score_text = " / ".join(f"{lbl}: {scores.get(k, 0)}" for k, lbl in SCORE_LABELS.items())
        content = (
            f"[Summary] {t.get('summary_ko', t.get('summary', ''))} "
            f"[배경] {t.get('background', '')} "
            f"[문제] {t.get('problem', '')} "
            f"[기능] {t.get('feature', '')}"
        )
        rows.append(_td(
            cycle_label(t.get("cycle_number", 0)),
            t.get("key", ""), t.get("summary", ""), t.get("reporter", ""),
            t.get("created", ""), t.get("due_date", ""),
            content, score_text, str(t.get("priority_score", 0)), t.get("brd_approval", ""),
        ))
    return f"<table><tbody>{''.join(rows)}</tbody></table>"


# ── 결과 3: 펜딩 티켓 현황 ────────────────────────────────
def _build_pending_html(tickets: list[dict]) -> str:
    pending = [t for t in tickets if t.get("brd_approval") == "Pending"]
    rows = [_th("회차", "Key", "Ticket Summary", "Reporter", "Created", "Due Date")]
    for t in pending:
        rows.append(_td(
            cycle_label(t.get("cycle_number", 0)),
            t.get("key", ""), t.get("summary", ""), t.get("reporter", ""),
            t.get("created", ""), t.get("due_date", ""),
        ))
    return f"<table><tbody>{''.join(rows)}</tbody></table>"


# ── 결과 4: 히스토리 아카이빙 (Expand Macro, Append) ─────────
def _build_history_expand_html(tickets: list[dict], cycle_n: int) -> str:
    label = cycle_label(cycle_n)
    rows = [_th("구분", "티켓 인입 수", "승인", "반려", "보류")]
    for rl, region in [("Total", None)] + [(r, r) for r in REGIONS]:
        rows.append(_td(
            rl,
            str(_cnt(tickets, region)),
            str(_cnt(tickets, region, "Approved")),
            str(_cnt(tickets, region, "Rejected")),
            str(_cnt(tickets, region, ["Pending", "Pre-BRD"])),
        ))
    table = f"<table><tbody>{''.join(rows)}</tbody></table>"
    return (
        f'<ac:structured-macro ac:name="expand">'
        f'<ac:parameter ac:name="title">{label} 마감 현황</ac:parameter>'
        f'<ac:rich-text-body>{table}</ac:rich-text-body>'
        f'</ac:structured-macro>'
    )


def update(tickets_with_analysis: list[dict], client: ConfluenceClient | None = None):
    if client is None:
        client = ConfluenceClient()

    page = client.find_page("doc2")
    page_id = page["id"]
    html, version, title = client.get_page_storage(page_id)

    current_cycle = max((t.get("cycle_number", 0) for t in tickets_with_analysis), default=0)

    # 결과 1·2·3: 덮어쓰기(Replace)
    html = client.replace_section(html, "AUTO_SUMMARY", _build_summary_html(tickets_with_analysis))
    html = client.replace_section(html, "AUTO_TABLE",   _build_table_html(tickets_with_analysis))
    html = client.replace_section(html, "AUTO_PENDING", _build_pending_html(tickets_with_analysis))

    # 결과 4: 히스토리 누적 추가(Append)
    html = client.append_to_section(html, "AUTO_HISTORY",
                                    _build_history_expand_html(tickets_with_analysis, current_cycle))

    client.update_page(page_id, title, html, version, "Doc2 현황 업데이트")
    print(f"[Doc2] 완료 — 총 {len(tickets_with_analysis)}건")
