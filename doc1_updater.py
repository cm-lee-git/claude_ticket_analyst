"""
Document 1: KKR OneApp 주간 보고 — New/Improvement 표 업데이트
업데이트 주기: 매주 월요일 10:00
"""
from lxml import etree
from confluence_client import ConfluenceClient
from cycle import cycle_label


SCORE_LABELS = {
    "urgency":               "시급성",
    "business_performance":  "사업 성과 기여",
    "customer_experience":   "고객 경험 영향도",
    "operational_efficiency":"운영 효율화",
    "global_reach":          "글로벌 파급 범위",
    "platform_strategy":     "플랫폼 운영 전략 연계도",
}


def _build_ticket_rows(tickets: list[dict], include_brd: bool) -> list[etree._Element]:
    rows = []
    for i, t in enumerate(tickets, 1):
        scores = t.get("scores", {})
        score_text = " / ".join(
            f"{label}: {scores.get(key, 0)}"
            for key, label in SCORE_LABELS.items()
        )
        cells = [
            str(i),
            cycle_label(t.get("cycle_number", 0)),
            t.get("key", ""),
            t.get("summary", ""),
            t.get("reporter", ""),
            t.get("created", ""),
            t.get("due_date", ""),
            # 내용
            f"[상태] {t.get('status', '')}\n"
            f"[Summary] {t.get('summary_ko', t.get('summary', ''))}\n"
            f"[배경] {t.get('background', '')}\n"
            f"[문제] {t.get('problem', '')}\n"
            f"[기능] {t.get('feature', '')}",
            # 항목별 분포
            score_text,
            # Priority 점수
            str(t.get("priority_score", 0)),
        ]
        if include_brd:
            cells.append(t.get("brd_approval", ""))

        tr = etree.Element("tr")
        for text in cells:
            td = etree.SubElement(tr, "td")
            p = etree.SubElement(td, "p")
            p.text = text
        rows.append(tr)
    return rows


def _rebuild_section_table(tickets: list[dict], include_brd: bool) -> etree._Element:
    table = etree.Element("table")
    tbody = etree.SubElement(table, "tbody")

    # 헤더
    headers = ["#", "Cycle", "Key", "Ticket Summary", "Reporter",
               "Created", "Due Date", "내용", "항목별 분포", "Priority 점수"]
    if include_brd:
        headers.append("BRD 승인 여부")
    tr_head = etree.SubElement(tbody, "tr")
    for h in headers:
        th = etree.SubElement(tr_head, "th")
        p = etree.SubElement(th, "p")
        p.text = h

    # 데이터 행
    for row in _build_ticket_rows(tickets, include_brd):
        tbody.append(row)

    return table


def update(tickets_with_analysis: list[dict], client: ConfluenceClient | None = None):
    """Doc1 페이지의 New/Improvement 표를 Pre-BRD / Post-BRD 두 섹션으로 재구성하여 업데이트."""
    if client is None:
        client = ConfluenceClient()

    page = client.find_page("doc1")
    page_id = page["id"]
    xml, version, title = client.get_page_storage(page_id)

    pre_brd = [t for t in tickets_with_analysis if t.get("brd_approval") == "Pre-BRD"]
    post_brd = [t for t in tickets_with_analysis if t.get("brd_approval") != "Pre-BRD"]

    root = client.parse_xml(xml)
    tables = client.find_tables(root)

    target = client.find_table_by_header(tables, "Ticket Summary")
    if target is None:
        raise RuntimeError("New/Improvement 표를 페이지에서 찾을 수 없습니다.")

    parent = target.getparent()
    idx = list(parent).index(target)

    # 기존 표 제거 후 두 섹션 삽입
    parent.remove(target)

    def insert_section(label: str, data: list[dict], include_brd: bool, pos: int) -> int:
        h3 = etree.Element("h3")
        h3.text = label
        parent.insert(pos, h3)
        tbl = _rebuild_section_table(data, include_brd)
        parent.insert(pos + 1, tbl)
        return pos + 2

    idx = insert_section("Pre-BRD", pre_brd, include_brd=False, pos=idx)
    insert_section("Post-BRD", post_brd, include_brd=True, pos=idx)

    new_xml = client.serialize_xml(root)
    client.update_page(page_id, title, new_xml, version, "Doc1 주간 업데이트")
    print(f"[Doc1] 업데이트 완료 — Pre-BRD: {len(pre_brd)}건 / Post-BRD: {len(post_brd)}건")
