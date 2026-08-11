"""
Document 2: 신규/개선 전체 현황 — 새 페이지 생성 방식
원본(71237682) 구조와 동일하게 생성:
  Section 0: 스크리닝 기준 (정적)
  Section 1: 전체 현황 + 회차별 트래킹 + 마감 히스토리 expand
  Section 2: KR 티켓 히스토리 (승인/보류/반려 × Pre-BRD/회차별 expand)
  Section 3: EU 티켓 히스토리
  Section 4: HQ GBCXD 및 타부문 티켓 히스토리
"""
from collections import defaultdict
from datetime import datetime

from confluence_client import ConfluenceClient
from config import DOC_PAGE_IDS
from cycle import cycle_label, get_cycle_bounds

JIRA_BROWSE = "https://hmg.atlassian.net/browse"


def _key_link(key: str) -> str:
    """Jira 티켓 키 → 하이퍼링크 HTML."""
    if not key:
        return ""
    return f'<a href="{JIRA_BROWSE}/{key}">{key}</a>'

# ── 상수 ────────────────────────────────────────────────────────
SCORE_LABELS = [
    "시급성", "사업 성과 기여", "고객 경험 영향도",
    "운영 효율화", "글로벌 파급 범위", "플랫폼 운영 전략 연계도",
]
SCORE_KEYS = [
    "urgency", "business_performance", "customer_experience",
    "operational_efficiency", "global_reach", "platform_strategy",
]

REGION_LABEL = {"KR": "RHQ KR", "EU": "RHQ EU", "HQ": "HQ GBCXD 및 타부문"}

# 각 섹션에 포함되는 region 값 (Global → KR+EU 모두)
_KR_REGIONS  = ("KR",)
_EU_REGIONS  = ("EU",)
_HQ_REGIONS  = ("HQ",)
APPROVAL_LABEL = {"Approved": "승인", "보류": "보류", "반려": "반려"}

# 표 셀 배경 색상 (원본 71237682 기준)
GREY       = "#b3bac5"   # 헤더/라벨 배경
LIGHT_GREY = "#f4f5f7"   # 종합 현황 데이터 셀
KR_BLUE    = "#4c9aff"   # KR 열 헤더
EU_TEAL    = "#79e2f2"   # EU 열 헤더
HQ_GREEN   = "#57d9a3"   # HQ 열 헤더
TOTAL_BLUE = "#deebff"   # 트래킹 Total 행 데이터

# 참조 문서(71237682) 기준 colgroup 너비
CW = {
    "section1_overall":   [107, 159, 133, 133, 133, 133],      # 6열: 전체현황
    "section1_tracking":  [122, 108, 87, 92, 71, 90, 85, 106,  # 19열: 트래킹
                           83, 98, 81, 92, 92, 106, 87, 83, 92, 92, 92],
    "kr_approved":        [104, 93, 101, 167, 93, 93, 93,       # 12열: KR 승인
                           291, 93, 93, 93, 104],
    "kr_pending":         [208, 110, 110, 110, 110, 110,        # 14열: KR 보류 (항목분포 2열 추가)
                           110, 110, 110, 93, 93, 110, 110, 110],
    "kr_rejected":        [200, 132, 132, 135, 132, 132,        # 12열: KR 반려 (항목분포 2열 추가)
                           132, 132, 93, 93, 159, 132],
    "eu_approved":        [198, 122, 122, 122, 122, 122,        # 11열: EU 승인
                           122, 122, 122, 122, 122],
    "eu_pending":         [198, 122, 122, 122, 122, 122,        # 13열: EU 보류 (항목분포 2열 추가)
                           122, 122, 93, 93, 122, 122, 122],
    "eu_rejected":        [198, 122, 122, 122, 122, 122,        # 12열: EU 반려 (항목분포 2열 추가)
                           122, 122, 93, 93, 122, 122],
    "history":            [122, 108, 87, 92, 71, 90, 85, 106,  # 13열: 마감 히스토리
                           83, 98, 81, 92, 92],
}


# ── HTML 빌더 헬퍼 ───────────────────────────────────────────────
def _colgroup(widths):
    cols = "".join(f'<col style="width: {w}.0px;"/>' for w in widths)
    return f"<colgroup>{cols}</colgroup>"


def _table(widths, rows_html):
    cg = _colgroup(widths) if widths else ""
    return f"<table>{cg}<tbody>{''.join(rows_html)}</tbody></table>"


def _th(*headers):
    return "<tr>" + "".join(f"<th><p><strong>{h}</strong></p></th>" for h in headers) + "</tr>"


def _th_span(cells):
    """cells: list of (text, rowspan, colspan)"""
    parts = []
    for text, rs, cs in cells:
        attrs = (f' rowspan="{rs}"' if rs > 1 else "") + (f' colspan="{cs}"' if cs > 1 else "")
        parts.append(f"<th{attrs}><p><strong>{text}</strong></p></th>")
    return "<tr>" + "".join(parts) + "</tr>"


def _td(*cells, style=""):
    st = f' style="{style}"' if style else ""
    return "<tr>" + "".join(f"<td{st}><p>{c}</p></td>" for c in cells) + "</tr>"


def _p(text):
    return f"<p>{text}</p>"


def _p_bold(text):
    return f"<p><strong>{text}</strong></p>"


def _h2(text):
    return f"<h2>{text}</h2>"


def _h3(text):
    return f"<h3>{text}</h3>"


def _expand(title, content):
    return (
        f'<ac:structured-macro ac:name="expand">'
        f'<ac:parameter ac:name="title">{title}</ac:parameter>'
        f'<ac:rich-text-body>{content}</ac:rich-text-body>'
        f'</ac:structured-macro>'
    )


def _panel(bg_color, content):
    return (
        f'<ac:structured-macro ac:name="panel" ac:schema-version="1">'
        f'<ac:parameter ac:name="bgColor">{bg_color}</ac:parameter>'
        f'<ac:rich-text-body>{content}</ac:rich-text-body>'
        f'</ac:structured-macro>'
    )


def _c(tag, text, bg=None, rs=None, cs=None, bold_white=False, bold=False):
    """배경색·rowspan·colspan·흰 볼드·볼드 지원 셀 빌더."""
    attrs = ""
    if rs: attrs += f' rowspan="{rs}"'
    if cs: attrs += f' colspan="{cs}"'
    if bg: attrs += f' data-highlight-colour="{bg}"'
    if bold_white and text:
        content = f'<strong><span style="color: rgb(255,255,255);">{text}</span></strong>'
    elif bold and text:
        content = f'<strong>{text}</strong>'
    else:
        content = text
    return f'<{tag}{attrs}><p style="text-align: center;">{content}</p></{tag}>'


def _track_label(cycle_n):
    """트래킹 표 데이터 행 첫 셀 라벨: 'N회차 (M/D~M/D)' 형식."""
    if cycle_n == 0:
        from cycle import ANCHOR
        from datetime import date, timedelta
        end = ANCHOR - timedelta(days=1)
        return f"Pre-BRD (1/1~{end.month}/{end.day})"
    start, end = get_cycle_bounds(cycle_n)
    return f"{cycle_n}회차 ({start.month}/{start.day}~{end.month}/{end.day})"


def _no_tickets(prebrd=False):
    return _p("해당 사항 없음" if prebrd else "해당 티켓 없음")


def _score_mark(value):
    try:
        return "O" if float(value) > 0 else "X"
    except (ValueError, TypeError):
        return "X"


def _cycle_expand_title(cycle_n):
    start, end = get_cycle_bounds(cycle_n)
    return f"#Cycle {cycle_n} ({start.year}. {start.month}/{start.day}~{end.month}/{end.day})"


def _effective_approval(ticket):
    """분석 결과(rejection_code/hold_code)를 우선 반영한 최종 승인 상태."""
    if ticket.get("rejection_code"):
        return "반려"
    if ticket.get("hold_code"):
        return "보류"
    return ticket.get("brd_approval", "")


def _cnt(tickets, region=None, approval=None, transition=None):
    """티켓 수 카운트.
    transition: None=전체 / "direct"=보류 미경유 / "converted"=보류 경유
    """
    result = tickets
    if region:
        if isinstance(region, (list, tuple)):
            result = [t for t in result if t.get("region") in region]
        else:
            result = [t for t in result if t.get("region") == region]
    if approval:
        if isinstance(approval, list):
            result = [t for t in result if _effective_approval(t) in approval]
        else:
            result = [t for t in result if _effective_approval(t) == approval]
    if transition == "direct":
        result = [t for t in result if not t.get("was_pending", False)]
    elif transition == "converted":
        result = [t for t in result if t.get("was_pending", False)]
    return len(result)


def _get_all_cycles(tickets):
    return sorted({t.get("cycle_number", 0) for t in tickets if t.get("cycle_number", 0) > 0})


# ── 승인 티켓 테이블 (rowspan=6 스코어링, KR 12열 / EU·HQ 11열) ───
def _build_approved_table(tickets, widths, has_cycle_col, is_prebrd=False):
    tickets = sorted(tickets, key=lambda t: t.get("created", ""))
    if not tickets:
        return _no_tickets(prebrd=is_prebrd)

    last_col = "CCI 안건 상정 여부" if is_prebrd else "BRD 승인 여부"
    if has_cycle_col:
        # 항목 분포: 스코어 항목명(1열) + O/X값(1열) = colspan 2
        header = _th_span([
            ("#", 1, 1), ("회차", 1, 1), ("Key", 1, 1), ("Ticket Summary", 1, 1),
            ("Reporter", 1, 1), ("Created", 1, 1), ("Due date", 1, 1), ("내용", 1, 1),
            ("항목 분포", 1, 2), ("Priority 점수", 1, 1), (last_col, 1, 1),
        ])
    else:
        header = _th_span([
            ("#", 1, 1), ("Key", 1, 1), ("Ticket Summary", 1, 1),
            ("Reporter", 1, 1), ("Created", 1, 1), ("Due date", 1, 1), ("Summary", 1, 1),
            ("항목 분포", 1, 2), ("Priority Score", 1, 1), (last_col, 1, 1),
        ])

    def td_rs(text, rs=6):
        return f'<td rowspan="{rs}"><p>{text}</p></td>'

    def _content_html(t):
        feature_label = t.get("feature_label") or "기존 기능 개선"
        parts = []
        for label, key in [("Summary", "summary_ko"), ("배경", "background"),
                            ("문제", "problem"), (feature_label, "feature")]:
            val = t.get(key) or (t.get("summary", "") if key == "summary_ko" else "")
            if val:
                lines = [line.strip() for line in val.split("\n") if line.strip()] or [val.strip()]
                bullets = "".join(f"<li>{line}</li>" for line in lines)
                parts.append(f"<p><strong>&lt;{label}&gt;</strong></p><ul>{bullets}</ul>")
        return "".join(parts)

    rows = [header]
    for seq, t in enumerate(tickets, 1):
        scores = t.get("scores", {})
        priority = str(sum(1 for k in SCORE_KEYS[1:] if float(scores.get(k, 0)) > 0))
        brd_val = "" if is_prebrd else APPROVAL_LABEL.get(_effective_approval(t), "")
        content_html = _content_html(t)
        cycle_col = f'<td rowspan="6"><p>{cycle_label(t.get("cycle_number", 0))}</p></td>' if has_cycle_col else ""

        # Row 1
        rows.append(
            f"<tr>"
            f'{td_rs(str(seq))}'
            f'{cycle_col}'
            f'<td rowspan="6"><p>{_key_link(t.get("key", ""))}</p></td>'
            f'{td_rs(t.get("summary", ""))}'
            f'{td_rs(t.get("reporter", ""))}'
            f'{td_rs(t.get("created", ""))}'
            f'{td_rs(t.get("due_date", ""))}'
            f'<td rowspan="6">{content_html}</td>'
            f'<td><p>{SCORE_LABELS[0]}</p></td>'
            f'<td><p>{_score_mark(scores.get(SCORE_KEYS[0], 0))}</p></td>'
            f'{td_rs(priority)}'
            f'{td_rs(brd_val)}'
            f"</tr>"
        )
        # Rows 2-6
        for i in range(1, 6):
            rows.append(
                f"<tr>"
                f'<td><p>{SCORE_LABELS[i]}</p></td>'
                f'<td><p>{_score_mark(scores.get(SCORE_KEYS[i], 0))}</p></td>'
                f"</tr>"
            )

    return _table(widths, rows)


# ── 보류 티켓 테이블 (rowspan=6, 항목 분포 포함) ─────────────────
def _build_pending_table(tickets, widths, has_cycle_col, prebrd=False):
    tickets = sorted(tickets, key=lambda t: t.get("created", ""))
    if not tickets:
        return _no_tickets(prebrd=prebrd)

    if has_cycle_col:
        header = _th_span([
            ("#", 1, 1), ("회차", 1, 1), ("Key", 1, 1), ("Ticket Summary", 1, 1),
            ("Reporter", 1, 1), ("Created", 1, 1), ("Due date", 1, 1),
            ("보류 code", 1, 1), ("보류 사유", 1, 1),
            ("항목 분포", 1, 2),
            ("댓글 히스토리", 1, 1), ("최종 결과(승인/반려 전환 결과 및 사유 & 날짜)", 1, 1), ("IMG", 1, 1),
        ])
    else:
        header = _th_span([
            ("#", 1, 1), ("Key", 1, 1), ("Ticket Summary", 1, 1),
            ("Reporter", 1, 1), ("Created", 1, 1), ("Due date", 1, 1),
            ("보류 code", 1, 1), ("보류 사유", 1, 1),
            ("항목 분포", 1, 2),
            ("댓글 히스토리", 1, 1), ("최종 결과(승인/반려 전환 결과 및 사유 & 날짜)", 1, 1), ("IMG", 1, 1),
        ])

    def td_rs(text, rs=6):
        return f'<td rowspan="{rs}"><p>{text}</p></td>'

    rows = [header]
    for seq, t in enumerate(tickets, 1):
        hold_code = t.get("hold_code") or ""
        reason = t.get("hold_reason") or (t.get("background", "")[:150] if hold_code else "")
        scores = t.get("scores", {})
        cycle_col = f'<td rowspan="6"><p>{cycle_label(t.get("cycle_number", 0))}</p></td>' if has_cycle_col else ""

        rows.append(
            f"<tr>"
            f'{td_rs(str(seq))}'
            f'{cycle_col}'
            f'<td rowspan="6"><p>{_key_link(t.get("key", ""))}</p></td>'
            f'{td_rs(t.get("summary", ""))}'
            f'{td_rs(t.get("reporter", ""))}'
            f'{td_rs(t.get("created", ""))}'
            f'{td_rs(t.get("due_date", ""))}'
            f'{td_rs(hold_code)}'
            f'{td_rs(reason)}'
            f'<td><p>{SCORE_LABELS[0]}</p></td>'
            f'<td><p>{_score_mark(scores.get(SCORE_KEYS[0], 0))}</p></td>'
            f'{td_rs("")}'
            f'{td_rs("")}'
            f'{td_rs("")}'
            f"</tr>"
        )
        for i in range(1, 6):
            rows.append(
                f"<tr>"
                f'<td><p>{SCORE_LABELS[i]}</p></td>'
                f'<td><p>{_score_mark(scores.get(SCORE_KEYS[i], 0))}</p></td>'
                f"</tr>"
            )

    return _table(widths, rows)


# ── 반려 티켓 테이블 (rowspan=6, 항목 분포 포함) ─────────────────
def _build_rejected_table(tickets, widths, has_cycle_col, prebrd=False):
    tickets = sorted(tickets, key=lambda t: t.get("created", ""))
    if not tickets:
        return _no_tickets(prebrd=prebrd)

    if has_cycle_col:
        header = _th_span([
            ("#", 1, 1), ("회차", 1, 1), ("Key", 1, 1), ("Ticket Summary", 1, 1),
            ("Reporter", 1, 1), ("Created", 1, 1), ("Due date", 1, 1),
            ("반려 code", 1, 1), ("반려 사유", 1, 1),
            ("항목 분포", 1, 2),
            ("IMG", 1, 1),
        ])
    else:
        header = _th_span([
            ("#", 1, 1), ("Key", 1, 1), ("Ticket Summary", 1, 1),
            ("Reporter", 1, 1), ("Created", 1, 1), ("Due date", 1, 1),
            ("반려 code", 1, 1), ("반려 사유", 1, 1),
            ("항목 분포", 1, 2),
            ("IMG", 1, 1),
        ])

    def td_rs(text, rs=6):
        return f'<td rowspan="{rs}"><p>{text}</p></td>'

    rows = [header]
    for seq, t in enumerate(tickets, 1):
        rej_code = t.get("rejection_code") or ""
        reason = t.get("rejection_reason") or (t.get("problem", "")[:150] if rej_code else "")
        scores = t.get("scores", {})
        cycle_col = f'<td rowspan="6"><p>{cycle_label(t.get("cycle_number", 0))}</p></td>' if has_cycle_col else ""

        rows.append(
            f"<tr>"
            f'{td_rs(str(seq))}'
            f'{cycle_col}'
            f'<td rowspan="6"><p>{_key_link(t.get("key", ""))}</p></td>'
            f'{td_rs(t.get("summary", ""))}'
            f'{td_rs(t.get("reporter", ""))}'
            f'{td_rs(t.get("created", ""))}'
            f'{td_rs(t.get("due_date", ""))}'
            f'{td_rs(rej_code)}'
            f'{td_rs(reason)}'
            f'<td><p>{SCORE_LABELS[0]}</p></td>'
            f'<td><p>{_score_mark(scores.get(SCORE_KEYS[0], 0))}</p></td>'
            f'{td_rs("")}'
            f"</tr>"
        )
        for i in range(1, 6):
            rows.append(
                f"<tr>"
                f'<td><p>{SCORE_LABELS[i]}</p></td>'
                f'<td><p>{_score_mark(scores.get(SCORE_KEYS[i], 0))}</p></td>'
                f"</tr>"
            )

    return _table(widths, rows)


# ── Section 0: 스크리닝 기준 ─────────────────────────────────────
def _build_section0():
    intro_panel = _panel("#DEEBFF",
        "<p><strong>회차별 신규/개선 티켓 스크리닝 운영 및 의견에서 이력 관리 및 관련 내용</strong></p>"
        "<ul>"
        "<li><p>티켓 검토 기준: 티켓 생성 후 2 영업일 이내 승인 / 보류 / 반려 의견 전달</p></li>"
        "<li><p>페이지 업데이트 기준: 검토 완료 시점으로부터 1 영업일 이내 현황 수치 및 권역별 히스토리 반영</p></li>"
        "</ul>"
        "<p>▶ 본 문서</p>"
        "<p>ㅇ 티켓 스크리닝 현황 및 이력 관리</p>"
    )
    criteria_panel = _panel("#F4F5F7",
        "<ul>"
        "<li><p>스크리닝 진행 현황에 따라 승인 / 보류 / 반려 세 그룹으로 분류되며, 티켓 처리 과정에 필요한 세부 단계 및 관련 요청 사항</p></li>"
        "<li><p>보류 안내일로부터 10 영업일 이내 미보완 시 자동 반려 <strong>*별도 안내 필요</strong></p></li>"
        "</ul>"
    )
    code_table = _table(CW.get("section1_overall", []), [
        _th_span([("보류", 1, 3), ("반려", 1, 4)]),
        _th("code", "유형", "판단 기준", "해소 조건", "code", "유형", "판단 기준"),
        _td("H1", "필수 항목 누락", "BRD 필수 항목 미작성 (추진 배경, 기능 목록, IT 연동 등)", "BRD 보완 후 재검토",
            "R1", "평가 항목 전항목 미충족", "시급성 해당 없음 + 5개 평가 항목 합계 0점"),
        _td("H2", "구체성 부족", "작성 항목의 요건 구체성 부족 또는 구현 로직 불명확", "요건 구체화 후 재검토",
            "R2", "운영 범위 외", "OneApp 플랫폼 운영 범위 외 요청 (타 시스템·채널 소관)"),
        _td("H3", "정량 근거 부족", "스코어링 근거가 추정 수준, 정량 데이터 보완 필요", "정량 데이터 보완 후 재검토",
            "R3", "중복 티켓", "실질적으로 동일한 요건이 이미 진행 중인 티켓 존재"),
        _td("H4", "선행 조건 미충족", "타 티켓/프로젝트 완료 또는 정책 확정이 선행 필요", "선행 조건 해소 후 재검토",
            "R4", "방향성 배치", "글로벌 BPM 방향성 또는 리더십 결정 사항과 배치"),
    ])
    return [
        intro_panel,
        _h2("0. 티켓 스크리닝 기준"),
        criteria_panel,
        code_table,
        _p("*code : 처리 품질 리스트에 적용되는 트래킹 코드 - H=Hold / R=Reject"),
    ]


# ── Section 1: 스크리닝 현황 ──────────────────────────────────────
def _build_section1(tickets, current_cycle):
    # ── 종합 현황 표 (6열) ─────────────────────────────────────────
    # 헤더행: colspan=2 빈 셀(회색) + 항목명 4개(흰 볼드, 회색)
    h_row = (
        "<tr>"
        + _c("th", "", bg=GREY, cs=2)
        + _c("th", "티켓 인입 수", bg=GREY, bold_white=True)
        + _c("th", "승인",        bg=GREY, bold_white=True)
        + _c("th", "반려",        bg=GREY, bold_white=True)
        + _c("th", "보류",        bg=GREY, bold_white=True)
        + "</tr>"
    )
    # Total 행: colspan=2 회색 볼드 + 연회색 데이터
    total_row = (
        "<tr>"
        + _c("td", "Total", bg=GREY, cs=2, bold_white=True)
        + _c("td", str(_cnt(tickets)),                         bg=LIGHT_GREY)
        + _c("td", str(_cnt(tickets, approval="Approved")),    bg=LIGHT_GREY)
        + _c("td", str(_cnt(tickets, approval="반려")),    bg=LIGHT_GREY)
        + _c("td", str(_cnt(tickets, approval=["보류"])), bg=LIGHT_GREY)
        + "</tr>"
    )
    # RHQ KR 행: KR + Global 포함
    kr_row = (
        "<tr>"
        + _c("td", "RHQ", bg=GREY, rs=2, bold_white=True)
        + _c("td", "KR",  bg=GREY, bold_white=True)
        + _c("td", str(_cnt(tickets, _KR_REGIONS)))
        + _c("td", str(_cnt(tickets, _KR_REGIONS, "Approved")))
        + _c("td", str(_cnt(tickets, _KR_REGIONS, "반려")))
        + _c("td", str(_cnt(tickets, _KR_REGIONS, ["보류"])))
        + "</tr>"
    )
    # EU 행: EU + Global 포함
    eu_row = (
        "<tr>"
        + _c("td", "EU", bg=GREY, bold_white=True)
        + _c("td", str(_cnt(tickets, _EU_REGIONS)))
        + _c("td", str(_cnt(tickets, _EU_REGIONS, "Approved")))
        + _c("td", str(_cnt(tickets, _EU_REGIONS, "반려")))
        + _c("td", str(_cnt(tickets, _EU_REGIONS, ["보류"])))
        + "</tr>"
    )
    # HQ 행: HQ만 (Global 제외)
    hq_row = (
        "<tr>"
        + _c("td", "HQ",             bg=GREY, bold_white=True)
        + _c("td", "GBCXD 및 타부문", bg=GREY, bold_white=True)
        + _c("td", str(_cnt(tickets, _HQ_REGIONS)))
        + _c("td", str(_cnt(tickets, _HQ_REGIONS, "Approved")))
        + _c("td", str(_cnt(tickets, _HQ_REGIONS, "반려")))
        + _c("td", str(_cnt(tickets, _HQ_REGIONS, ["보류"])))
        + "</tr>"
    )
    overall_table = _table(CW["section1_overall"],
                           [h_row, total_row, kr_row, eu_row, hq_row])

    # ── 회차별 트래킹 표 (19열, 4행 헤더) ──────────────────────────
    # 포함 대상: Pre-BRD(0) + 모든 회차
    all_cycles = sorted({t.get("cycle_number", 0) for t in tickets})

    # 헤더 4행
    track_h1 = (
        "<tr>"
        + _c("th", "",    bg=GREY, rs=4)          # 회차 열 (rowspan=4, 빈 헤더)
        + _c("th", "RHQ", bg=GREY, cs=12, bold_white=True)
        + _c("th", "HQ",  bg=GREY, cs=6,  bold_white=True)
        + "</tr>"
    )
    track_h2 = (
        "<tr>"
        + _c("th", "KR",             bg=KR_BLUE,  cs=6, bold_white=True)
        + _c("td", "EU",             bg=EU_TEAL,  cs=6, bold_white=True)
        + _c("td", "GBCXD 및 타부문", bg=HQ_GREEN, cs=6, bold_white=True)
        + "</tr>"
    )
    track_h3 = (
        "<tr>"
        # KR
        + _c("th", "티켓 인입 수", bg=KR_BLUE, rs=2, bold_white=True)
        + _c("td", "승인",        bg=KR_BLUE, rs=2, bold_white=True)
        + _c("td", "반려",        bg=KR_BLUE, rs=2, bold_white=True)
        + _c("td", "보류",        bg=KR_BLUE, cs=3, bold_white=True)
        # EU
        + _c("td", "티켓 인입 수", bg=EU_TEAL, rs=2, bold_white=True)
        + _c("td", "승인",        bg=EU_TEAL, rs=2, bold_white=True)
        + _c("td", "반려",        bg=EU_TEAL, rs=2, bold_white=True)
        + _c("td", "보류",        bg=EU_TEAL, cs=3, bold_white=True)
        # HQ
        + _c("td", "티켓 인입 수", bg=HQ_GREEN, rs=2, bold_white=True)
        + _c("td", "승인",        bg=HQ_GREEN, rs=2, bold_white=True)
        + _c("td", "반려",        bg=HQ_GREEN, rs=2, bold_white=True)
        + _c("td", "보류",        bg=HQ_GREEN, cs=3, bold_white=True)
        + "</tr>"
    )
    track_h4 = (
        "<tr>"
        + _c("th", "보류 중",   bg=KR_BLUE, bold_white=True)
        + _c("td", "승인 전환", bg=KR_BLUE, bold_white=True)
        + _c("td", "반려 전환", bg=KR_BLUE, bold_white=True)
        + _c("td", "보류 중",   bg=EU_TEAL, bold_white=True)
        + _c("td", "승인 전환", bg=EU_TEAL, bold_white=True)
        + _c("td", "반려 전환", bg=EU_TEAL, bold_white=True)
        + _c("td", "보류 중",   bg=HQ_GREEN, bold_white=True)
        + _c("td", "승인 전환", bg=HQ_GREEN, bold_white=True)
        + _c("td", "반려 전환", bg=HQ_GREEN, bold_white=True)
        + "</tr>"
    )

    # 데이터 행: 회차별 (첫 셀 <th grey 볼드>, 나머지 <td>)
    def _dash(n: int) -> str:
        return "-" if n == 0 else str(n)

    track_data = []
    pend = ["보류"]
    for cn in all_cycles:
        cyc = [t for t in tickets if t.get("cycle_number") == cn]
        def _s(reg=None, appr=None, trans=None, _cyc=cyc):
            return _dash(_cnt(_cyc, reg, appr, transition=trans))
        row = (
            "<tr>"
            + _c("th", _track_label(cn), bg=GREY, bold_white=True)
            # KR: 인입, 승인(직접), 반려(직접), 보류중, 승인전환, 반려전환
            + _c("td", _s(_KR_REGIONS))
            + _c("td", _s(_KR_REGIONS, "Approved",  "direct"))
            + _c("td", _s(_KR_REGIONS, "반려",  "direct"))
            + _c("td", _s(_KR_REGIONS, pend))
            + _c("td", _s(_KR_REGIONS, "Approved",  "converted"))
            + _c("td", _s(_KR_REGIONS, "반려",  "converted"))
            # EU
            + _c("td", _s(_EU_REGIONS))
            + _c("td", _s(_EU_REGIONS, "Approved",  "direct"))
            + _c("td", _s(_EU_REGIONS, "반려",  "direct"))
            + _c("td", _s(_EU_REGIONS, pend))
            + _c("td", _s(_EU_REGIONS, "Approved",  "converted"))
            + _c("td", _s(_EU_REGIONS, "반려",  "converted"))
            # HQ
            + _c("td", _s(_HQ_REGIONS))
            + _c("td", _s(_HQ_REGIONS, "Approved",  "direct"))
            + _c("td", _s(_HQ_REGIONS, "반려",  "direct"))
            + _c("td", _s(_HQ_REGIONS, pend))
            + _c("td", _s(_HQ_REGIONS, "Approved",  "converted"))
            + _c("td", _s(_HQ_REGIONS, "반려",  "converted"))
            + "</tr>"
        )
        track_data.append(row)

    # Total 행: 회색 볼드 라벨 + 연파란 데이터
    def _st(reg, appr=None, trans=None):
        return _dash(_cnt(tickets, reg, appr, transition=trans))
    total_track = (
        "<tr>"
        + _c("th", "Total", bg=GREY, bold_white=True)
        + _c("td", _st(_KR_REGIONS),                            bg=TOTAL_BLUE, bold=True)
        + _c("td", _st(_KR_REGIONS, "Approved",  "direct"),    bg=TOTAL_BLUE, bold=True)
        + _c("td", _st(_KR_REGIONS, "반려",  "direct"),    bg=TOTAL_BLUE, bold=True)
        + _c("td", _st(_KR_REGIONS, pend),                     bg=TOTAL_BLUE, bold=True)
        + _c("td", _st(_KR_REGIONS, "Approved",  "converted"), bg=TOTAL_BLUE, bold=True)
        + _c("td", _st(_KR_REGIONS, "반려",  "converted"), bg=TOTAL_BLUE, bold=True)
        + _c("td", _st(_EU_REGIONS),                            bg=TOTAL_BLUE, bold=True)
        + _c("td", _st(_EU_REGIONS, "Approved",  "direct"),    bg=TOTAL_BLUE, bold=True)
        + _c("td", _st(_EU_REGIONS, "반려",  "direct"),    bg=TOTAL_BLUE, bold=True)
        + _c("td", _st(_EU_REGIONS, pend),                     bg=TOTAL_BLUE, bold=True)
        + _c("td", _st(_EU_REGIONS, "Approved",  "converted"), bg=TOTAL_BLUE, bold=True)
        + _c("td", _st(_EU_REGIONS, "반려",  "converted"), bg=TOTAL_BLUE, bold=True)
        + _c("td", _st(_HQ_REGIONS),                            bg=TOTAL_BLUE, bold=True)
        + _c("td", _st(_HQ_REGIONS, "Approved",  "direct"),    bg=TOTAL_BLUE, bold=True)
        + _c("td", _st(_HQ_REGIONS, "반려",  "direct"),    bg=TOTAL_BLUE, bold=True)
        + _c("td", _st(_HQ_REGIONS, pend),                     bg=TOTAL_BLUE, bold=True)
        + _c("td", _st(_HQ_REGIONS, "Approved",  "converted"), bg=TOTAL_BLUE, bold=True)
        + _c("td", _st(_HQ_REGIONS, "반려",  "converted"), bg=TOTAL_BLUE, bold=True)
        + "</tr>"
    )

    tracking_table = _table(CW["section1_tracking"],
                            [track_h1, track_h2, track_h3, track_h4]
                            + track_data + [total_track])

    # 회차별 마감 히스토리 섹션 (표 자체는 Doc2-1 별도 페이지에 생성)
    doc21_folder_id = DOC_PAGE_IDS["doc21"]
    doc21_link = (
        f'<ac:link><ri:page ri:content-title="2-1) 회차별 마감 히스토리"/></ac:link>'
    )
    history_section = (
        _h3("■ 회차별 마감 히스토리")
        + _p(f'참고: {doc21_link}')
    )

    return [
        _h2("1. 티켓 스크리닝 현황"),
        _p(f"(업데이트) {datetime.now().strftime('%y.%m.%d')} 기준"),
        _h3("■ 종합 현황 (Screen Shot)"),
        overall_table,
        _h3("■ 회차별 트래킹 현황"),
        tracking_table,
        history_section,
    ]


# ── Section 2-4: 지역별 티켓 히스토리 ────────────────────────────
def _build_region_section(tickets, region_code, section_num, approved_widths,
                          pending_widths, rejected_widths, has_cycle_col):
    # Global 티켓은 KR+EU 섹션 모두에 포함, HQ는 HQ만
    region_tickets = [t for t in tickets if t.get("region") in {
        "KR": _KR_REGIONS, "EU": _EU_REGIONS, "HQ": _HQ_REGIONS
    }[region_code]]
    # 전체 티켓 기준 사이클 목록 사용 → 티켓 없는 회차도 펼치기 생성
    cycles = _get_all_cycles(tickets)
    region_name = {"KR": "KR", "EU": "EU", "HQ": "HQ GBCXD 및 타부문"}[region_code]

    def _filter(cyc=None, appr=None):
        result = region_tickets
        if cyc == 0:
            result = [t for t in result if t.get("cycle_number", 0) == 0]
        elif cyc is not None:
            result = [t for t in result if t.get("cycle_number") == cyc]
        if appr:
            if isinstance(appr, list):
                result = [t for t in result if _effective_approval(t) in appr]
            else:
                result = [t for t in result if _effective_approval(t) == appr]
        return result

    parts = [_h2(f"{section_num}. {region_name} 티켓 히스토리")]

    # 승인 티켓
    parts.append(_p_bold(f"{section_num}.1. 승인 티켓"))
    parts.append(_expand("Pre-BRD",
        _build_approved_table(_filter(0, "Approved"), approved_widths, has_cycle_col, is_prebrd=True)))
    for cn in cycles:
        parts.append(_expand(_cycle_expand_title(cn),
            _build_approved_table(_filter(cn, "Approved"), approved_widths, has_cycle_col)))

    # 보류 티켓: Pending 상태만 (BRD 제출 후 공식 보류; Pre-BRD 미제출 티켓 제외)
    parts.append(_p_bold(f"{section_num}.2. 보류 티켓"))
    parts.append(_expand("Pre-BRD",
        _build_pending_table(_filter(0, "Pending"), pending_widths, has_cycle_col, prebrd=True)))
    for cn in cycles:
        parts.append(_expand(_cycle_expand_title(cn),
            _build_pending_table(_filter(cn, "Pending"), pending_widths, has_cycle_col)))

    # 반려 티켓
    parts.append(_p_bold(f"{section_num}.3. 반려 티켓"))
    parts.append(_expand("Pre-BRD",
        _build_rejected_table(_filter(0, "반려"), rejected_widths, has_cycle_col, prebrd=True)))
    for cn in cycles:
        parts.append(_expand(_cycle_expand_title(cn),
            _build_rejected_table(_filter(cn, "반려"), rejected_widths, has_cycle_col)))

    return parts


# ── 메인 업데이트 함수 ──────────────────────────────────────────
def update(tickets_with_analysis: list[dict], client: ConfluenceClient | None = None):
    if client is None:
        client = ConfluenceClient()

    current_cycle = max((t.get("cycle_number", 0) for t in tickets_with_analysis), default=0)

    _toc = (
        '<ac:structured-macro ac:name="toc" ac:schema-version="1">'
        '<ac:parameter ac:name="style">none</ac:parameter>'
        '</ac:structured-macro>'
    )
    sections = [_toc]
    sections += _build_section1(tickets_with_analysis, current_cycle)
    sections += _build_region_section(
        tickets_with_analysis, "KR", 2,
        CW["kr_approved"], CW["kr_pending"], CW["kr_rejected"], has_cycle_col=True)
    sections += _build_region_section(
        tickets_with_analysis, "EU", 3,
        CW["eu_approved"], CW["eu_pending"], CW["eu_rejected"], has_cycle_col=False)
    sections += _build_region_section(
        tickets_with_analysis, "HQ", 4,
        CW["eu_approved"], CW["eu_pending"], CW["eu_rejected"], has_cycle_col=False)

    html = "\n".join(sections)

    timestamp = datetime.now().strftime("%m-%d %H:%M")
    title = f"{timestamp} 신규/개선 전체 현황 (AI 생성)"
    parent_id = DOC_PAGE_IDS["doc2"]

    result = client.create_page(parent_id, title, html)
    new_id = result.get("id", "")
    print(f"[Doc2] 완료  총 {len(tickets_with_analysis)}건")
    print(f"[Doc2] 새 페이지: {title}  (id={new_id})")


def update_with_new_tickets(tickets_with_analysis: list[dict],
                            client: ConfluenceClient | None = None):
    """월 16시, 화~금 16시: 당일 신규 티켓 있으면 기존 최신 페이지를 전체 재구성하여 업데이트."""
    if client is None:
        client = ConfluenceClient()

    if not tickets_with_analysis:
        print("[Doc2-Daily] 당일 신규 티켓 없음 → 종료")
        return

    # 기존 최신 doc2 페이지 찾기 (제목 내림차순)
    children = client.get_child_pages(DOC_PAGE_IDS["doc2"])
    if not children:
        print("[Doc2-Daily] 기존 페이지 없음 → 종료")
        return
    latest = sorted(children, key=lambda p: p["title"], reverse=True)[0]
    page_id = latest["id"]
    _, version, title = client.get_page_storage(page_id)
    print(f"[Doc2-Daily] 업데이트 대상: {title} (id={page_id})")

    # 전체 데이터로 페이지 HTML 재구성 후 UPDATE (create 아님)
    current_cycle = max((t.get("cycle_number", 0) for t in tickets_with_analysis), default=0)
    _toc = (
        '<ac:structured-macro ac:name="toc" ac:schema-version="1">'
        '<ac:parameter ac:name="style">none</ac:parameter>'
        '</ac:structured-macro>'
    )
    sections = [_toc]
    sections += _build_section1(tickets_with_analysis, current_cycle)
    sections += _build_region_section(
        tickets_with_analysis, "KR", 2,
        CW["kr_approved"], CW["kr_pending"], CW["kr_rejected"], has_cycle_col=True)
    sections += _build_region_section(
        tickets_with_analysis, "EU", 3,
        CW["eu_approved"], CW["eu_pending"], CW["eu_rejected"], has_cycle_col=False)
    sections += _build_region_section(
        tickets_with_analysis, "HQ", 4,
        CW["eu_approved"], CW["eu_pending"], CW["eu_rejected"], has_cycle_col=False)
    html = "\n".join(sections)

    client.update_page(page_id, title, html, version,
                       message=f"Daily: 신규 {len(tickets_with_analysis)}건 반영")
    print(f"[Doc2-Daily] 완료  총 {len(tickets_with_analysis)}건 → 페이지 업데이트")
