"""
Document 2: 신규/개선 전체 현황 업데이트

Confluence 페이지에 아래 마커가 미리 삽입되어 있어야 합니다:
  <p>AUTO_SUMMARY_START</p>    ... <p>AUTO_SUMMARY_END</p>    ← 종합 현황 (Replace)
  <p>AUTO_TRACKING_START</p>   ... <p>AUTO_TRACKING_END</p>   ← 회차별 트래킹 현황 (Replace)
  <p>AUTO_TABLE_START</p>      ... <p>AUTO_TABLE_END</p>       ← 상세 티켓 테이블 (Replace)
  <p>AUTO_PENDING_START</p>    ... <p>AUTO_PENDING_END</p>     ← 보류 중 현황 (Replace)
  <p>AUTO_MATRIX_START</p>     ... <p>AUTO_MATRIX_END</p>      ← 회차별 마감 히스토리 매트릭스 (Replace)
  <p>AUTO_KR_HISTORY_START</p> ... <p>AUTO_KR_HISTORY_END</p> ← KR 티켓 히스토리 (Replace)
  <p>AUTO_EU_HISTORY_START</p> ... <p>AUTO_EU_HISTORY_END</p> ← EU 티켓 히스토리 (Replace)
  <p>AUTO_HQ_HISTORY_START</p> ... <p>AUTO_HQ_HISTORY_END</p> ← HQ 티켓 히스토리 (Replace)
  <p>AUTO_HISTORY_START</p>    ... <p>AUTO_HISTORY_END</p>     ← 회차 Expand 아카이브 (Append)
"""
from collections import defaultdict

from confluence_client import ConfluenceClient
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


# ── 공통 헬퍼 ───────────────────────────────────────────────────
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
    """cells: list of (text, rowspan, colspan)"""
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
    return f"<table><tbody>{''.join(rows)}</tbody></table>"


# ── 섹션 2: 회차별 트래킹 현황 ──────────────────────────────────
def _build_cycle_tracking_html(tickets: list[dict], current_cycle: int) -> str:
    """
    현재 회차 티켓의 지역별 현황.
    보류 중 세부: 보류중(Pending) / 승인 전환(Approved) / 반려 전환(Rejected)
    """
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
            str(_cnt(cur, region, ["Pending", "Pre-BRD"])),   # 보류중
            str(_cnt(cur, region, "Approved")),                # 승인 전환 (≈ Approved)
            str(_cnt(cur, region, "Rejected")),                # 반려 전환 (≈ Rejected)
        ))

    rows = [header1, header2] + data_rows
    label_str = cycle_label(current_cycle)
    title_row = f"<tr><td colspan=\"7\"><p>{label_str} 트래킹 현황</p></td></tr>"
    return f"<table><tbody>{title_row}{''.join(rows)}</tbody></table>"


# ── 섹션 3: 상세 티켓 테이블 (기본 + 분석) ──────────────────────
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
    return f"<table><tbody>{''.join(rows)}</tbody></table>"


# ── 섹션 4: 보류 중 현황 ────────────────────────────────────────
def _build_pending_html(tickets: list[dict]) -> str:
    pending = [t for t in tickets if t.get("brd_approval") in ("Pending", "Pre-BRD")]
    rows = [_th("회차", "Key", "Ticket Summary", "Reporter", "Created", "Due Date", "BRD 상태", "보류 유형")]
    for t in pending:
        hold_code = t.get("hold_code") or ""
        rows.append(_td(
            cycle_label(t.get("cycle_number", 0)),
            t.get("key", ""), t.get("summary", ""), t.get("reporter", ""),
            t.get("created", ""), t.get("due_date", ""),
            t.get("brd_approval", ""), hold_code,
        ))
    return f"<table><tbody>{''.join(rows)}</tbody></table>"


# ── 섹션 5: 회차별 마감 히스토리 매트릭스 ──────────────────────
def _build_matrix_html(tickets: list[dict]) -> str:
    """
    행: 회차 / 열: RHQ KR · RHQ EU · HQ GBCXD 및 타부문
    셀: 인입 N / 승인 N / 반려 N / 보류 N
    """
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
            cell("RHQ KR"),
            cell("RHQ EU"),
            cell("HQ GBCXD 및 타부문"),
            cell(None),
        ))
    return f"<table><tbody>{''.join(rows)}</tbody></table>"


# ── 섹션 6: 지역별 티켓 히스토리 ────────────────────────────────
def _build_regional_history_html(tickets: list[dict], region: str) -> str:
    """
    특정 지역의 티켓을 회차별로 묶어 표시.
    region: "RHQ KR" | "RHQ EU" | "HQ GBCXD 및 타부문"
    """
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

    return f"<table><tbody>{''.join(rows)}</tbody></table>"


# ── 섹션 7: 히스토리 아카이빙 (Expand Macro, Append) ────────────
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


# ── 메인 업데이트 함수 ──────────────────────────────────────────
def update(tickets_with_analysis: list[dict], client: ConfluenceClient | None = None):
    if client is None:
        client = ConfluenceClient()

    page = client.find_page("doc2")
    page_id = page["id"]
    html, version, title = client.get_page_storage(page_id)

    current_cycle = max((t.get("cycle_number", 0) for t in tickets_with_analysis), default=0)

    # Replace 섹션들
    html = client.replace_section(html, "AUTO_SUMMARY",
                                  _build_summary_html(tickets_with_analysis))
    html = client.replace_section(html, "AUTO_TRACKING",
                                  _build_cycle_tracking_html(tickets_with_analysis, current_cycle))
    html = client.replace_section(html, "AUTO_TABLE",
                                  _build_table_html(tickets_with_analysis))
    html = client.replace_section(html, "AUTO_PENDING",
                                  _build_pending_html(tickets_with_analysis))
    html = client.replace_section(html, "AUTO_MATRIX",
                                  _build_matrix_html(tickets_with_analysis))
    html = client.replace_section(html, "AUTO_KR_HISTORY",
                                  _build_regional_history_html(tickets_with_analysis, "RHQ KR"))
    html = client.replace_section(html, "AUTO_EU_HISTORY",
                                  _build_regional_history_html(tickets_with_analysis, "RHQ EU"))
    html = client.replace_section(html, "AUTO_HQ_HISTORY",
                                  _build_regional_history_html(tickets_with_analysis, "HQ GBCXD 및 타부문"))

    # Append 섹션 (히스토리 누적)
    html = client.append_to_section(html, "AUTO_HISTORY",
                                    _build_history_expand_html(tickets_with_analysis, current_cycle))

    client.update_page(page_id, title, html, version, "Doc2 현황 업데이트")
    print(f"[Doc2] 완료  총 {len(tickets_with_analysis)}건")
