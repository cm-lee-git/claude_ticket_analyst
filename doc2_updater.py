"""
Document 2: 신규/개선 전체 현황 — 새 페이지 생성 방식
실행마다 타임스탬프가 붙은 새 페이지를 doc2 부모 페이지 하위에 생성.
"""
from collections import defaultdict
from datetime import datetime

from confluence_client import ConfluenceClient
from config import DOC_PAGE_IDS
from cycle import cycle_label

REGIONS = ["RHQ KR", "RHQ EU", "HQ GBCXD 및 타부문"]
REGION_MAP = {"KR": "RHQ KR", "EU": "RHQ EU", "HQ": "HQ GBCXD 및 타부문"}
REGION_KEYS = {"RHQ KR": "KR", "RHQ EU": "EU", "HQ GBCXD 및 타부문": "HQ"}

SCORE_LABELS = {
    "urgency":                "시급성",
    "business_performance":   "사업 성과 기여",
    "customer_experience":    "고객 경험 영향도",
    "operational_efficiency": "운영 효율화",
    "global_reach":           "글로벌 파급 범위",
    "platform_strategy":      "플랫폼 운영 전략 연계도",
}

# 참조 문서(71237682) 기준 열 너비
COL_WIDTHS = {
    "summary":   [200, 150, 150, 150, 150],                             # 5열: 종합 현황
    "tracking":  [107, 159, 133, 133, 133, 133, 133],                  # 7열: 회차별 트래킹
    "table":     [60, 110, 180, 260, 90, 90, 90, 300, 90, 90, 90],    # 11열: 상세 티켓
    "pending":   [60, 110, 250, 100, 90, 90, 100, 100],                # 8열: 보류 현황
    "matrix":    [100, 220, 220, 220, 180],                             # 5열: 매트릭스
    "history":   [60, 110, 250, 100, 90, 90, 90],                      # 7열: 지역별 히스토리
}


# ── 공통 헬퍼 ───────────────────────────────────────────────────
def _colgroup(widths: list[float]) -> str:
    cols = "".join(f'<col style="width: {w}.0px;"/>' for w in widths)
    return f"<colgroup>{cols}</colgroup>"


def _with_colgroup(table_html: str, widths: list[float]) -> str:
    return table_html.replace("<table>", f"<table>{_colgroup(widths)}", 1)


def _cnt(tickets, region=None, approval=None) -> int:
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

def _th_span(cells: list[tuple]) -> str:
    parts = []
    for text, rs, cs in cells:
        attrs = ""
        if rs > 1:
            attrs += f' rowspan="{rs}"'
        if cs > 1:
            attrs += f' colspan="{cs}"'
        parts.append(f"<th{attrs}><p>{text}</p></th>")
    return "<tr>" + "".join(parts) + "</tr>"

def _td(*cells) -> str:
    return "<tr>" + "".join(f"<td><p>{c}</p></td>" for c in cells) + "</tr>"

def _h2(text: str) -> str:
    return f"<h2>{text}</h2>"


# ── 섹션 1: 종합 현황 ───────────────────────────────────────────
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
    table = f"<table><tbody>{''.join(rows)}</tbody></table>"
    return _with_colgroup(table, COL_WIDTHS["summary"])


# ── 섹션 2: 회차별 트래킹 현황 ──────────────────────────────────
def _build_cycle_tracking_html(tickets: list[dict], current_cycle: int) -> str:
    cur = [t for t in tickets if t.get("cycle_number") == current_cycle]

    header1 = _th_span([
        ("구분",       2, 1),
        ("티켓 인입 수", 2, 1),
        ("승인",       2, 1),
        ("반려",       2, 1),
        ("보류 중",    1, 3),
    ])
    header2 = _th_span([
        ("보류중",    1, 1),
        ("승인 전환", 1, 1),
        ("반려 전환", 1, 1),
    ])

    data_rows = []
    for label, region in [("Total", None), ("RHQ KR", "RHQ KR"),
                           ("RHQ EU", "RHQ EU"), ("HQ GBCXD 및 타부문", "HQ GBCXD 및 타부문")]:
        data_rows.append(_td(
            label,
            str(_cnt(cur, region)),
            str(_cnt(cur, region, "Approved")),
            str(_cnt(cur, region, "Rejected")),
            str(_cnt(cur, region, ["Pending", "Pre-BRD"])),
            str(_cnt(cur, region, "Approved")),
            str(_cnt(cur, region, "Rejected")),
        ))

    label_str = cycle_label(current_cycle)
    title_row = f"<tr><td colspan=\"7\"><p>{label_str} 트래킹 현황</p></td></tr>"
    rows = [header1, header2] + data_rows
    table = f"<table><tbody>{title_row}{''.join(rows)}</tbody></table>"
    return _with_colgroup(table, COL_WIDTHS["tracking"])


# ── 섹션 3: 상세 티켓 테이블 ────────────────────────────────────
def _build_table_html(tickets: list[dict]) -> str:
    rows = [_th("회차", "Key", "Ticket Summary", "Reporter", "Created", "Due Date",
                "내용", "항목별 분포", "Priority 점수", "BRD 승인 여부", "유형 코드")]
    for t in tickets:
        scores = t.get("scores", {})
        score_text = " / ".join(
            f"{lbl}: {scores.get(k, 0)}" for k, lbl in SCORE_LABELS.items()
        )
        content_parts = [
            f"[요약] {t.get('summary_ko') or t.get('summary', '')}",
            f"[배경] {t.get('background', '')}",
            f"[문제] {t.get('problem', '')}",
            f"[기능] {t.get('feature', '')}",
        ]
        content = " ".join(p for p in content_parts if not p.endswith("] "))
        type_code = t.get("hold_code") or t.get("rejection_code") or ""
        rows.append(_td(
            cycle_label(t.get("cycle_number", 0)),
            t.get("key", ""), t.get("summary", ""), t.get("reporter", ""),
            t.get("created", ""), t.get("due_date", ""),
            content, score_text,
            str(t.get("priority_score", 0)), t.get("brd_approval", ""), type_code,
        ))
    table = f"<table><tbody>{''.join(rows)}</tbody></table>"
    return _with_colgroup(table, COL_WIDTHS["table"])


# ── 섹션 4: 보류 중 현황 ────────────────────────────────────────
def _build_pending_html(tickets: list[dict]) -> str:
    pending = [t for t in tickets if t.get("brd_approval") in ("Pending", "Pre-BRD")]
    rows = [_th("회차", "Key", "Ticket Summary", "Reporter", "Created", "Due Date", "BRD 상태", "보류 유형")]
    for t in pending:
        rows.append(_td(
            cycle_label(t.get("cycle_number", 0)),
            t.get("key", ""), t.get("summary", ""), t.get("reporter", ""),
            t.get("created", ""), t.get("due_date", ""),
            t.get("brd_approval", ""), t.get("hold_code") or "",
        ))
    table = f"<table><tbody>{''.join(rows)}</tbody></table>"
    return _with_colgroup(table, COL_WIDTHS["pending"])


# ── 섹션 5: 회차별 마감 히스토리 매트릭스 ──────────────────────
def _build_matrix_html(tickets: list[dict]) -> str:
    cycles = sorted({t.get("cycle_number", 0) for t in tickets})
    rows = [_th("회차", "RHQ KR", "RHQ EU", "HQ GBCXD 및 타부문", "Total")]
    for cn in cycles:
        cycle_tickets = [t for t in tickets if t.get("cycle_number") == cn]

        def cell(region=None):
            sub = [t for t in cycle_tickets
                   if region is None or REGION_MAP.get(t.get("region")) == region]
            approved = sum(1 for t in sub if t.get("brd_approval") == "Approved")
            rejected = sum(1 for t in sub if t.get("brd_approval") == "Rejected")
            pending  = sum(1 for t in sub if t.get("brd_approval") in ("Pending", "Pre-BRD"))
            return f"인입 {len(sub)} / 승인 {approved} / 반려 {rejected} / 보류 {pending}"

        rows.append(_td(
            cycle_label(cn),
            cell("RHQ KR"), cell("RHQ EU"), cell("HQ GBCXD 및 타부문"), cell(None),
        ))
    table = f"<table><tbody>{''.join(rows)}</tbody></table>"
    return _with_colgroup(table, COL_WIDTHS["matrix"])


# ── 섹션 6: 지역별 티켓 히스토리 ────────────────────────────────
def _build_regional_history_html(tickets: list[dict], region: str) -> str:
    region_key = REGION_KEYS.get(region, "HQ")
    filtered = [t for t in tickets if t.get("region") == region_key]

    by_cycle: dict[int, list[dict]] = defaultdict(list)
    for t in filtered:
        by_cycle[t.get("cycle_number", 0)].append(t)

    rows = [_th("회차", "Key", "Ticket Summary", "Reporter", "Created", "Due Date", "BRD 승인 여부")]
    for cn in sorted(by_cycle.keys()):
        for t in by_cycle[cn]:
            rows.append(_td(
                cycle_label(cn),
                t.get("key", ""), t.get("summary", ""), t.get("reporter", ""),
                t.get("created", ""), t.get("due_date", ""),
                t.get("brd_approval", ""),
            ))
    if not filtered:
        rows.append(_td(region, "-", "-", "-", "-", "-", "-"))

    table = f"<table><tbody>{''.join(rows)}</tbody></table>"
    return _with_colgroup(table, COL_WIDTHS["history"])


# ── 메인 업데이트 함수 ──────────────────────────────────────────
def update(tickets_with_analysis: list[dict], client: ConfluenceClient | None = None):
    if client is None:
        client = ConfluenceClient()

    current_cycle = max((t.get("cycle_number", 0) for t in tickets_with_analysis), default=0)

    sections = [
        _h2("종합 현황"),
        _build_summary_html(tickets_with_analysis),
        _h2(f"{cycle_label(current_cycle)} 트래킹 현황"),
        _build_cycle_tracking_html(tickets_with_analysis, current_cycle),
        _h2("티켓 상세 현황"),
        _build_table_html(tickets_with_analysis),
        _h2("보류 중 현황"),
        _build_pending_html(tickets_with_analysis),
        _h2("회차별 마감 히스토리"),
        _build_matrix_html(tickets_with_analysis),
        _h2("KR 티켓 히스토리"),
        _build_regional_history_html(tickets_with_analysis, "RHQ KR"),
        _h2("EU 티켓 히스토리"),
        _build_regional_history_html(tickets_with_analysis, "RHQ EU"),
        _h2("HQ 티켓 히스토리"),
        _build_regional_history_html(tickets_with_analysis, "HQ GBCXD 및 타부문"),
    ]
    html = "\n".join(sections)

    timestamp = datetime.now().strftime("%m-%d %H:%M")
    title = f"{timestamp} 신규/개선 전체 현황 (AI 생성)"
    parent_id = DOC_PAGE_IDS["doc2"]

    result = client.create_page(parent_id, title, html)
    new_id = result.get("id", "")
    print(f"[Doc2] 완료  총 {len(tickets_with_analysis)}건")
    print(f"[Doc2] 새 페이지: {title}  (id={new_id})")
