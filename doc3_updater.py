"""
Document 3: (Kia) 신규/개선 (AI 생성) — Smart Updater
- Cycle별 표 구조 (1티켓 = 7행, rowspan 포함)
- 기존 티켓: Key로 탐색 후 셀 값 업데이트
- 신규 티켓: 7행 rowspan 블록을 해당 Cycle 표 맨 아래 추가
- 새 Cycle: 새 표 자동 생성
"""
from bs4 import BeautifulSoup, Tag
from confluence_client import ConfluenceClient
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


def _get_existing_keys(table: Tag) -> dict[str, Tag]:
    keys = {}
    for row in table.find_all('tr'):
        cells = row.find_all(['td', 'th'])
        if len(cells) > 8 and any(int(c.get('rowspan', 1)) > 1 for c in cells):
            key_text = cells[2].get_text(strip=True)
            if key_text and key_text not in keys:
                keys[key_text] = row
    return keys


def _find_cycle_table(soup: BeautifulSoup, cycle_n: int) -> Tag | None:
    label = cycle_label(cycle_n)
    for table in soup.find_all('table'):
        first = table.find('tr')
        if first and label in first.get_text():
            return table
    return None


def _create_cycle_table(soup: BeautifulSoup, cycle_n: int) -> Tag:
    """새 Cycle 표 생성 (타이틀행 + 헤더행)."""
    from cycle import get_cycle_bounds
    import datetime
    start, end = get_cycle_bounds(cycle_n)
    label = f"{cycle_label(cycle_n)} ({start.strftime('%Y %m/%d')}~{end.strftime('%m/%d')})"

    table = soup.new_tag('table')
    tbody = soup.new_tag('tbody')

    # 타이틀행
    tr_t = soup.new_tag('tr')
    td_t = soup.new_tag('td')
    td_t['colspan'] = '11'
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


def _update_ticket_row(first_row: Tag, ticket: dict, soup: BeautifulSoup):
    cells = first_row.find_all(['td', 'th'])
    scores = ticket.get('scores', {})

    def set_cell(idx, text):
        if idx < len(cells):
            for c in list(cells[idx].children):
                c.extract()
            p = soup.new_tag('p')
            p.string = str(text)
            cells[idx].append(p)

    set_cell(3, ticket.get('summary', ''))
    set_cell(4, ticket.get('reporter', ''))
    set_cell(5, ticket.get('created', ''))
    set_cell(6, ticket.get('due_date', ''))
    set_cell(8, str(scores.get(SCORE_KEYS[0], '')))  # 시급성 점수

    next_row = first_row.find_next_sibling('tr')
    for i in range(1, 7):
        if next_row is None:
            break
        row_cells = next_row.find_all(['td', 'th'])
        if len(row_cells) == 2:
            for c in list(row_cells[1].children):
                c.extract()
            p = soup.new_tag('p')
            val = scores.get(SCORE_KEYS[i], '') if i < 6 else ticket.get('priority_score', '')
            p.string = str(val)
            row_cells[1].append(p)
        next_row = next_row.find_next_sibling('tr')


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

    # Row 1
    tr1 = soup.new_tag('tr')
    tr1.append(td(seq_num, rowspan=7))
    tr1.append(td(ticket.get('region', ''), rowspan=7))         # Target
    tr1.append(td(ticket.get('key', ''), rowspan=7))            # Ticket No.
    tr1.append(td(ticket.get('summary', ''), rowspan=7))        # Summary
    tr1.append(td(ticket.get('reporter', ''), rowspan=7))
    tr1.append(td(ticket.get('created', ''), rowspan=7))
    tr1.append(td(ticket.get('due_date', ''), rowspan=7))
    tr1.append(td(SCORE_LABELS[0]))                             # 시급성 레이블
    tr1.append(td(scores.get(SCORE_KEYS[0], '')))               # 시급성 점수
    tr1.append(td('', rowspan=7))                               # CCI Escalation
    tr1.append(td('', rowspan=7))                               # Deployment Plan
    tr1.append(td('', rowspan=7))                               # Remark
    rows.append(tr1)

    # Rows 2~7: 나머지 스코어링
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

    page = client.find_page("doc3")
    page_id = page["id"]
    html, version, title = client.get_page_storage(page_id)
    soup = BeautifulSoup(html, 'html.parser')

    # Cycle별로 그룹화
    from collections import defaultdict
    by_cycle: dict[int, list[dict]] = defaultdict(list)
    for t in tickets_with_analysis:
        by_cycle[t.get('cycle_number', 0)].append(t)

    for cycle_n in sorted(by_cycle.keys(), reverse=True):
        tickets = by_cycle[cycle_n]
        table = _find_cycle_table(soup, cycle_n)
        if table is None:
            table = _create_cycle_table(soup, cycle_n)
            soup.append(table)

        existing_keys = _get_existing_keys(table)
        tbody = table.find('tbody') or table
        seq_start = len(existing_keys) + 1

        for t in tickets:
            key = t.get('key', '')
            if key in existing_keys:
                _update_ticket_row(existing_keys[key], t, soup)
            else:
                rows = _build_ticket_block(soup, t, seq_start)
                seq_start += 1
                for row in rows:
                    tbody.append(row)

    new_html = str(soup)
    client.update_page(page_id, title, new_html, version, "Doc3 Smart Update")
    print(f"[Doc3] 완료 — 총 {len(tickets_with_analysis)}건")
