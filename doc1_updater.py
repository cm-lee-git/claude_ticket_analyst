"""
Document 1: KKR OneApp 주간 보고 — New/Improvement 표 업데이트
업데이트 주기: 매주 월요일 10:00

Confluence 페이지에 아래 마커가 미리 삽입되어 있어야 합니다:
  <!-- AUTO_PRE_BRD_START --> ... <!-- AUTO_PRE_BRD_END -->
  <!-- AUTO_POST_BRD_START --> ... <!-- AUTO_POST_BRD_END -->
"""
from confluence_client import ConfluenceClient
from cycle import cycle_label

SCORE_LABELS = {
    "urgency":                "시급성",
    "business_performance":   "사업 성과 기여",
    "customer_experience":    "고객 경험 영향도",
    "operational_efficiency": "운영 효율화",
    "global_reach":           "글로벌 파급 범위",
    "platform_strategy":      "플랫폼 운영 전략 연계도",
}


def _build_table_html(tickets: list[dict], include_brd: bool) -> str:
    headers = ["#", "Cycle", "Key", "Ticket Summary", "Reporter",
               "Created", "Due Date", "내용", "항목별 분포", "Priority 점수"]
    if include_brd:
        headers.append("BRD 승인 여부")

    header_row = "".join(f"<th><p>{h}</p></th>" for h in headers)
    rows = [f"<tr>{header_row}</tr>"]

    for i, t in enumerate(tickets, 1):
        scores = t.get("scores", {})
        score_text = " / ".join(f"{lbl}: {scores.get(k, 0)}" for k, lbl in SCORE_LABELS.items())
        content = (
            f"[상태] {t.get('status', '')} "
            f"[Summary] {t.get('summary_ko', t.get('summary', ''))} "
            f"[배경] {t.get('background', '')} "
            f"[문제] {t.get('problem', '')} "
            f"[기능] {t.get('feature', '')}"
        )
        cells = [
            str(i),
            cycle_label(t.get("cycle_number", 0)),
            t.get("key", ""),
            t.get("summary", ""),
            t.get("reporter", ""),
            t.get("created", ""),
            t.get("due_date", ""),
            content,
            score_text,
            str(t.get("priority_score", 0)),
        ]
        if include_brd:
            cells.append(t.get("brd_approval", ""))

        cell_html = "".join(f"<td><p>{c}</p></td>" for c in cells)
        rows.append(f"<tr>{cell_html}</tr>")

    return f"<table><tbody>{''.join(rows)}</tbody></table>"


def update(tickets_with_analysis: list[dict], client: ConfluenceClient | None = None):
    if client is None:
        client = ConfluenceClient()

    page = client.find_page("doc1")
    page_id = page["id"]
    html, version, title = client.get_page_storage(page_id)

    pre_brd  = [t for t in tickets_with_analysis if t.get("brd_approval") == "Pre-BRD"]
    post_brd = [t for t in tickets_with_analysis if t.get("brd_approval") != "Pre-BRD"]

    html = client.replace_section(html, "AUTO_PRE_BRD",  _build_table_html(pre_brd,  include_brd=False))
    html = client.replace_section(html, "AUTO_POST_BRD", _build_table_html(post_brd, include_brd=True))

    client.update_page(page_id, title, html, version, "Doc1 주간 업데이트")
    print(f"[Doc1] 완료 — Pre-BRD: {len(pre_brd)}건 / Post-BRD: {len(post_brd)}건")
