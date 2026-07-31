"""
Document 3: (Kia) 신규/개선 업데이트

Confluence 페이지에 아래 마커가 미리 삽입되어 있어야 합니다:
  <!-- AUTO_BASIC_START --> ... <!-- AUTO_BASIC_END -->
  <!-- AUTO_SCORING_START --> ... <!-- AUTO_SCORING_END -->
"""
from confluence_client import ConfluenceClient

SCORE_LABELS = {
    "urgency":                "시급성",
    "business_performance":   "사업 성과 기여",
    "customer_experience":    "고객 경험 영향도",
    "operational_efficiency": "운영 효율화",
    "global_reach":           "글로벌 파급 범위",
    "platform_strategy":      "플랫폼 운영 전략 연계도",
}


def _th(*headers) -> str:
    return "<tr>" + "".join(f"<th><p>{h}</p></th>" for h in headers) + "</tr>"

def _td(*cells) -> str:
    return "<tr>" + "".join(f"<td><p>{c}</p></td>" for c in cells) + "</tr>"


def _build_basic_html(tickets: list[dict]) -> str:
    rows = [_th("Target", "Ticket Number", "Ticket Summary", "Reporter", "Created", "Due Date")]
    for t in tickets:
        rows.append(_td(
            t.get("region", ""), t.get("key", ""), t.get("summary", ""),
            t.get("reporter", ""), t.get("created", ""), t.get("due_date", ""),
        ))
    return f"<table><tbody>{''.join(rows)}</tbody></table>"


def _build_scoring_html(tickets: list[dict]) -> str:
    rows = [_th("Key", *SCORE_LABELS.values(), "Priority 점수")]
    for t in tickets:
        scores = t.get("scores", {})
        rows.append(_td(
            t.get("key", ""),
            *[str(scores.get(k, 0)) for k in SCORE_LABELS],
            str(t.get("priority_score", 0)),
        ))
    return f"<table><tbody>{''.join(rows)}</tbody></table>"


def update(tickets_with_analysis: list[dict], client: ConfluenceClient | None = None):
    if client is None:
        client = ConfluenceClient()

    page = client.find_page("doc3")
    page_id = page["id"]
    html, version, title = client.get_page_storage(page_id)

    html = client.replace_section(html, "AUTO_BASIC",   _build_basic_html(tickets_with_analysis))
    html = client.replace_section(html, "AUTO_SCORING", _build_scoring_html(tickets_with_analysis))

    client.update_page(page_id, title, html, version, "Doc3 업데이트")
    print(f"[Doc3] 완료 — 총 {len(tickets_with_analysis)}건")
