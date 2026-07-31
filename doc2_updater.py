"""
Document 2: 신규/개선 전체 현황 업데이트
업데이트 기준:
  - 티켓 검토: 생성 후 2 영업일 이내
  - 페이지 업데이트: 검토 완료 후 1 영업일 이내
  - 스크리닝: 보류 안내일로부터 10 영업일 이내 미보완 시 자동 반려
"""
from collections import defaultdict
from lxml import etree
from confluence_client import ConfluenceClient
from cycle import cycle_label


REGIONS = ["RHQ KR", "RHQ EU", "HQ GBCXD 및 타부문"]
REGION_MAP = {"KR": "RHQ KR", "EU": "RHQ EU", "HQ": "HQ GBCXD 및 타부문"}
SCORE_LABELS = {
    "urgency":               "시급성",
    "business_performance":  "사업 성과 기여",
    "customer_experience":   "고객 경험 영향도",
    "operational_efficiency":"운영 효율화",
    "global_reach":          "글로벌 파급 범위",
    "platform_strategy":     "플랫폼 운영 전략 연계도",
}


def _count(tickets, region=None, approval=None):
    result = tickets
    if region:
        result = [t for t in result if REGION_MAP.get(t.get("region")) == region]
    if approval:
        if isinstance(approval, list):
            result = [t for t in result if t.get("brd_approval") in approval]
        else:
            result = [t for t in result if t.get("brd_approval") == approval]
    return len(result)


def _build_summary_table(tickets: list[dict]) -> etree._Element:
    table = etree.Element("table")
    tbody = etree.SubElement(table, "tbody")

    headers = ["구분", "티켓 인입 수", "승인", "반려", "보류"]
    tr = etree.SubElement(tbody, "tr")
    for h in headers:
        th = etree.SubElement(tr, "th")
        th.text = h

    rows = [
        ("Total", None),
        ("RHQ KR", "RHQ KR"),
        ("RHQ EU", "RHQ EU"),
        ("HQ GBCXD 및 타부문", "HQ GBCXD 및 타부문"),
    ]
    for label, region in rows:
        tr = etree.SubElement(tbody, "tr")
        for val in [
            label,
            str(_count(tickets, region)),
            str(_count(tickets, region, "Approved")),
            str(_count(tickets, region, "Rejected")),
            str(_count(tickets, region, ["Pending", "Pre-BRD"])),
        ]:
            td = etree.SubElement(tr, "td")
            td.text = val
    return table


def _build_cycle_tracking_table(tickets: list[dict]) -> etree._Element:
    cycles = sorted({t.get("cycle_number", 0) for t in tickets})
    table = etree.Element("table")
    tbody = etree.SubElement(table, "tbody")

    headers = ["회차", "구분", "티켓 인입 수", "승인", "반려",
               "보류중", "승인 전환", "반려 전환"]
    tr = etree.SubElement(tbody, "tr")
    for h in headers:
        th = etree.SubElement(tr, "th")
        th.text = h

    for cycle_n in cycles:
        cycle_tickets = [t for t in tickets if t.get("cycle_number") == cycle_n]
        label = cycle_label(cycle_n)
        rows_data = [("Total", None)] + [(r, r) for r in REGIONS]
        for i, (rl, region) in enumerate(rows_data):
            tr = etree.SubElement(tbody, "tr")
            if i == 0:
                td_cycle = etree.SubElement(tr, "td")
                td_cycle.set("rowspan", str(len(rows_data)))
                td_cycle.text = label
            td_region = etree.SubElement(tr, "td")
            td_region.text = rl
            for val in [
                str(_count(cycle_tickets, region)),
                str(_count(cycle_tickets, region, "Approved")),
                str(_count(cycle_tickets, region, "Rejected")),
                str(_count(cycle_tickets, region, "Pending")),
                "0",  # 승인 전환 (이력 추적 필요 — 현재 스냅샷에선 0)
                "0",  # 반려 전환
            ]:
                td = etree.SubElement(tr, "td")
                td.text = val
    return table


def _build_basic_info_table(tickets: list[dict]) -> etree._Element:
    table = etree.Element("table")
    tbody = etree.SubElement(table, "tbody")
    tr = etree.SubElement(tbody, "tr")
    for h in ["회차", "Key", "Ticket Summary", "Reporter", "Created", "Due Date"]:
        th = etree.SubElement(tr, "th")
        th.text = h
    for t in tickets:
        tr = etree.SubElement(tbody, "tr")
        for val in [
            cycle_label(t.get("cycle_number", 0)),
            t.get("key", ""),
            t.get("summary", ""),
            t.get("reporter", ""),
            t.get("created", ""),
            t.get("due_date", ""),
        ]:
            td = etree.SubElement(tr, "td")
            td.text = val
    return table


def _build_generated_info_table(tickets: list[dict]) -> etree._Element:
    table = etree.Element("table")
    tbody = etree.SubElement(table, "tbody")
    tr = etree.SubElement(tbody, "tr")
    for h in ["Key", "내용", "항목별 분포", "Priority 점수", "BRD 승인 여부"]:
        th = etree.SubElement(tr, "th")
        th.text = h
    for t in tickets:
        scores = t.get("scores", {})
        score_text = " / ".join(
            f"{lbl}: {scores.get(k, 0)}" for k, lbl in SCORE_LABELS.items()
        )
        content = (
            f"[Summary] {t.get('summary_ko', t.get('summary', ''))}\n"
            f"[배경] {t.get('background', '')}\n"
            f"[문제] {t.get('problem', '')}\n"
            f"[기능] {t.get('feature', '')}"
        )
        tr = etree.SubElement(tbody, "tr")
        for val in [
            t.get("key", ""),
            content,
            score_text,
            str(t.get("priority_score", 0)),
            t.get("brd_approval", ""),
        ]:
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

    page = client.find_page("doc2")
    page_id = page["id"]
    xml, version, title = client.get_page_storage(page_id)
    root = client.parse_xml(xml)

    # A) 종합 현황 표
    _replace_or_append_table(root, "티켓 인입 수", _build_summary_table(tickets_with_analysis), client)

    # A) 회차별 트래킹 현황 표
    _replace_or_append_table(root, "회차", _build_cycle_tracking_table(tickets_with_analysis), client)

    # B) 기본 티켓 정보 표
    _replace_or_append_table(root, "Ticket Summary", _build_basic_info_table(tickets_with_analysis), client)

    # C) 신규 생성 정보 표
    _replace_or_append_table(root, "항목별 분포", _build_generated_info_table(tickets_with_analysis), client)

    new_xml = client.serialize_xml(root)
    client.update_page(page_id, title, new_xml, version, "Doc2 현황 업데이트")
    print(f"[Doc2] 업데이트 완료 — 총 {len(tickets_with_analysis)}건")
