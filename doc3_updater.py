"""
Document 3: (Kia) 신규/개선 업데이트
업데이트 기준:
  - 티켓 검토: 생성 후 2 영업일 이내
  - 페이지 업데이트: 검토 완료 후 1 영업일 이내
"""
from lxml import etree
from confluence_client import ConfluenceClient


SCORE_LABELS = {
    "urgency":               "시급성",
    "business_performance":  "사업 성과 기여",
    "customer_experience":   "고객 경험 영향도",
    "operational_efficiency":"운영 효율화",
    "global_reach":          "글로벌 파급 범위",
    "platform_strategy":     "플랫폼 운영 전략 연계도",
}


def _build_basic_table(tickets: list[dict]) -> etree._Element:
    table = etree.Element("table")
    tbody = etree.SubElement(table, "tbody")
    tr = etree.SubElement(tbody, "tr")
    for h in ["Target", "Ticket Number", "Ticket Summary", "Reporter", "Created", "Due Date"]:
        th = etree.SubElement(tr, "th")
        th.text = h
    for t in tickets:
        tr = etree.SubElement(tbody, "tr")
        for val in [
            t.get("region", ""),
            t.get("key", ""),
            t.get("summary", ""),
            t.get("reporter", ""),
            t.get("created", ""),
            t.get("due_date", ""),
        ]:
            td = etree.SubElement(tr, "td")
            td.text = val
    return table


def _build_scoring_table(tickets: list[dict]) -> etree._Element:
    table = etree.Element("table")
    tbody = etree.SubElement(table, "tbody")
    tr = etree.SubElement(tbody, "tr")
    for h in ["Key"] + list(SCORE_LABELS.values()) + ["Priority 점수"]:
        th = etree.SubElement(tr, "th")
        th.text = h
    for t in tickets:
        scores = t.get("scores", {})
        tr = etree.SubElement(tbody, "tr")
        vals = [t.get("key", "")] + [str(scores.get(k, 0)) for k in SCORE_LABELS] + [str(t.get("priority_score", 0))]
        for val in vals:
            td = etree.SubElement(tr, "td")
            td.text = val
    return table


def _replace_or_append_table(root: etree._Element, keyword: str, new_table: etree._Element, client: ConfluenceClient):
    tables = client.find_tables(root)
    existing = client.find_table_by_header(tables, keyword)
    if existing is not None:
        parent = existing.getparent()
        idx = list(parent).index(existing)
        parent.remove(existing)
        parent.insert(idx, new_table)
    else:
        root.append(new_table)


def update(tickets_with_analysis: list[dict], client: ConfluenceClient | None = None):
    if client is None:
        client = ConfluenceClient()

    page = client.find_page("doc3")
    page_id = page["id"]
    xml, version, title = client.get_page_storage(page_id)
    root = client.parse_xml(xml)

    # A) 기본 티켓 정보
    _replace_or_append_table(root, "Ticket Number", _build_basic_table(tickets_with_analysis), client)

    # B) Scoring
    _replace_or_append_table(root, "시급성", _build_scoring_table(tickets_with_analysis), client)

    new_xml = client.serialize_xml(root)
    client.update_page(page_id, title, new_xml, version, "Doc3 업데이트")
    print(f"[Doc3] 업데이트 완료 — 총 {len(tickets_with_analysis)}건")
