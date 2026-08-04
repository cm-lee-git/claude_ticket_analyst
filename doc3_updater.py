"""
Document 3: (Kia) 신규/개선 — 새 페이지 생성 방식
실행마다 타임스탬프가 붙은 새 페이지를 doc3 부모 페이지 하위에 생성.
Cycle별 표 구조 (1티켓 = 7행, rowspan 포함).
"""
from collections import defaultdict
from datetime import datetime

from bs4 import BeautifulSoup, Tag
from confluence_client import ConfluenceClient
from config import DOC_PAGE_IDS
from cycle import cycle_label, get_cycle_bounds

SCORE_LABELS = [
    "시급성 (Urgency)", "사업 성과 기여 (Business Impact)",
    "고객 경험 영향도 (Customer Experience)", "운영 효율화 (Operational Efficiency)",
    "글로벌 파급 범위 (Global Reach)", "플랫폼 운영 전략 연계도 (Platform Strategy)",
    "Total Score",
]
SCORE_KEYS = [
    "urgency", "business_performance", "customer_experience",
    "operational_efficiency", "global_reach", "platform_strategy",
    "priority_score",
]

# 참조 문서(71172124) 기준 열 너비 (12열)
COL_WIDTHS = [126, 109, 179, 515, 140, 135, 122, 252, 221, 167, 154, 154]


def _create_cycle_table(soup: BeautifulSoup, cycle_n: int) -> Tag:
    """새 Cycle 표 생성 (colgroup + 타이틀행 + 헤더행)."""
    start, end = get_cycle_bounds(cycle_n)
    label = f"{cycle_label(cycle_n)} ({start.strftime('%Y %m/%d')}~{end.strftime('%m/%d')})"

    table = soup.new_tag('table')

    # 열 너비 colgroup
    colgroup = soup.new_tag('colgroup')
    for w in COL_WIDTHS:
        col = soup.new_tag('col', style=f"width: {w}.0px;")
        colgroup.append(col)
    table.append(colgroup)

    tbody = soup.new_tag('tbody')

    # 타이틀행
    tr_t = soup.new_tag('tr')
    td_t = soup.new_tag('td')
    td_t['colspan'] = '12'
    p = soup.new_tag('p')
    p.string = label
    td_t.append(p)
    tr_t.append(td_t)
    tbody.append(tr_t)

    # 헤더행
    col_headers = [
        ('Global Prioritization', 1), ('Target', 1), ('Ticket No.', 1),
        ('Ticket Summary (Title)', 1), ('Reporter', 1), ('Created', 1), ('Due date', 1),
        ('New/Improvement Ticket Scoring (GBCXD)', 2),
        ('CCI Escalation', 1), ('Expected Deployment Plan', 1), ('Remark', 1),
    ]
    tr_h = soup.new_tag('tr')
    for text, colspan in col_headers:
        th = soup.new_tag('th')
        if colspan > 1:
            th['colspan'] = str(colspan)
        p = soup.new_tag('p')
        p.string = text
        th.append(p)
        tr_h.append(th)
    tbody.append(tr_h)
    table.append(tbody)
    return table


def _build_ticket_block(soup: BeautifulSoup, ticket: dict, seq_num: int) -> list[Tag]:
    """7행 티켓 블록 생성."""
    scores = ticket.get('scores', {})

    def td(text, rowspan=1, colspan=1):
        cell = soup.new_tag('td')
        if rowspan > 1:
            cell['rowspan'] = str(rowspan)
        if colspan > 1:
            cell['colspan'] = str(colspan)
        p = soup.new_tag('p')
        p.string = str(text)
        cell.append(p)
        return cell

    rows = []
    tr1 = soup.new_tag('tr')
    tr1.append(td(seq_num, rowspan=7))
    tr1.append(td(ticket.get('region', ''), rowspan=7))
    tr1.append(td(ticket.get('key', ''), rowspan=7))
    tr1.append(td(ticket.get('summary', ''), rowspan=7))
    tr1.append(td(ticket.get('reporter', ''), rowspan=7))
    tr1.append(td(ticket.get('created', ''), rowspan=7))
    tr1.append(td(ticket.get('due_date', ''), rowspan=7))
    tr1.append(td(SCORE_LABELS[0]))
    tr1.append(td(scores.get(SCORE_KEYS[0], '')))
    tr1.append(td('', rowspan=7))
    tr1.append(td('', rowspan=7))
    tr1.append(td('', rowspan=7))
    rows.append(tr1)

    for i in range(1, 7):
        tr = soup.new_tag('tr')
        tr.append(td(SCORE_LABELS[i]))
        val = scores.get(SCORE_KEYS[i], '') if i < 6 else ticket.get('priority_score', '')
        tr.append(td(val))
        rows.append(tr)

    return rows


def update(tickets_with_analysis: list[dict], client: ConfluenceClient | None = None):
    if client is None:
        client = ConfluenceClient()

    soup = BeautifulSoup("", 'html.parser')

    by_cycle: dict[int, list[dict]] = defaultdict(list)
    for t in tickets_with_analysis:
        by_cycle[t.get('cycle_number', 0)].append(t)

    for cycle_n in sorted(by_cycle.keys(), reverse=True):
        tickets = by_cycle[cycle_n]
        table = _create_cycle_table(soup, cycle_n)
        tbody = table.find('tbody')
        for i, t in enumerate(tickets, start=1):
            for row in _build_ticket_block(soup, t, i):
                tbody.append(row)
        soup.append(table)

    timestamp = datetime.now().strftime("%m-%d %H:%M")
    title = f"{timestamp} (Kia) 신규/개선 (AI 생성)"
    parent_id = DOC_PAGE_IDS["doc3"]

    result = client.create_page(parent_id, title, str(soup))
    new_id = result.get("id", "")
    print(f"[Doc3] 완료  총 {len(tickets_with_analysis)}건")
    print(f"[Doc3] 새 페이지: {title}  (id={new_id})")
