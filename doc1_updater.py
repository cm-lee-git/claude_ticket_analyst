"""
Document 1: KKR OneApp 주간 보고 (AI 생성) — Smart Updater
- 기존 티켓: Key로 탐색 후 셀 값 업데이트
- 신규 티켓: 6행 rowspan 블록 추가
- Pre-BRD / Post-BRD 섹션 구분
업데이트 주기: 매주 월요일 10:00
"""
import re
from bs4 import BeautifulSoup, Tag
from confluence_client import ConfluenceClient
from cycle import cycle_label

SCORE_LABELS = [
    "시급성", "사업 성과 기여", "고객 경험 영향도",
    "운영 효율화", "글로벌 파급 범위", "플랫폼 운영 전략 연계도",
]
SCORE_KEYS = [
    "urgency", "business_performance", "customer_experience",
    "operational_efficiency", "global_reach", "platform_strategy",
]

KEY_RE = re.compile(r'^(CCIPRJ|KCCIVOC|KEUVOCOP)-\d+$')


def _score_mark(value) -> str:
    """점수 > 0 이면 O, 아니면 X."""
    try:
        return 'O' if float(value) > 0 else 'X'
    except (ValueError, TypeError):
        return 'X'


def _count_o(scores: dict) -> str:
    """항목별 O 개수 반환 (0~6)."""
    return str(sum(1 for k in SCORE_KEYS if float(scores.get(k, 0)) > 0))


def _fill_content_cell(cell: Tag, ticket: dict, soup: BeautifulSoup):
    """내용 셀을 <Summary>/<배경>/<문제>/<기능> 형식으로 채움."""
    for child in list(cell.children):
        child.extract()

    feature_label = ticket.get('feature_label') or '기존 기능 개선'
    sections = [
        ('Summary',     ticket.get('summary_ko') or ticket.get('summary', '')),
        ('배경',        ticket.get('background', '')),
        ('문제',        ticket.get('problem', '')),
        (feature_label, ticket.get('feature', '')),
    ]
    for label, content in sections:
        if content:
            p_label = soup.new_tag('p')
            strong = soup.new_tag('strong')
            strong.string = f'<{label}>'
            p_label.append(strong)
            cell.append(p_label)
            p_content = soup.new_tag('p')
            p_content.string = content
            cell.append(p_content)


def _find_key_idx(cells: list[Tag]) -> int:
    """Jira Key 패턴과 일치하는 셀 인덱스 반환. 없으면 -1."""
    for i, c in enumerate(cells):
        if KEY_RE.match(c.get_text(strip=True)):
            return i
    return -1


def _find_section_table(soup: BeautifulSoup, section_text: str) -> Tag | None:
    for table in soup.find_all('table'):
        first_row = table.find('tr')
        if first_row and section_text in first_row.get_text():
            return table
    return None


def _get_existing_keys(table: Tag) -> dict[str, Tag]:
    """표에서 Jira Key → 첫 번째 데이터행 매핑 반환."""
    keys = {}
    for row in table.find_all('tr'):
        cells = row.find_all(['td', 'th'])
        if not any(int(c.get('rowspan', 1)) > 1 for c in cells):
            continue
        for cell in cells:
            text = cell.get_text(strip=True)
            if KEY_RE.match(text) and text not in keys:
                keys[text] = row
                break
    return keys


def _update_ticket_row(first_row: Tag, ticket: dict, soup: BeautifulSoup):
    """기존 티켓의 첫 번째 행 + 이후 5개 점수 행을 업데이트."""
    cells = first_row.find_all(['td', 'th'])
    scores = ticket.get('scores', {})

    key_idx = _find_key_idx(cells)
    if key_idx < 0:
        return  # Key를 찾지 못하면 스킵

    def set_cell(offset, text):
        idx = key_idx + offset
        if idx < len(cells):
            for c in list(cells[idx].children):
                c.extract()
            p = soup.new_tag('p')
            p.string = str(text)
            cells[idx].append(p)

    # key_idx 기준 상대 위치
    # +0=Key(skip), +1=Summary, +2=Reporter, +3=Created, +4=DueDate, +5=내용, +6=레이블(skip), +7=점수, +8=Priority, +9=BRD
    set_cell(1, ticket.get('summary', ''))
    set_cell(2, ticket.get('reporter', ''))
    set_cell(3, ticket.get('created', ''))
    set_cell(4, ticket.get('due_date', ''))

    content_idx = key_idx + 5
    if content_idx < len(cells):
        _fill_content_cell(cells[content_idx], ticket, soup)

    set_cell(7, _score_mark(scores.get(SCORE_KEYS[0], 0)))   # 시급성 O/X
    set_cell(8, str(ticket.get('priority_score', '')))
    brd_val = _count_o(scores) if ticket.get('brd_approval') != 'Pre-BRD' else ''
    set_cell(9, brd_val)

    # 이후 5개 점수 행 업데이트
    next_row = first_row.find_next_sibling('tr')
    for i in range(1, 6):
        if next_row is None:
            break
        row_cells = next_row.find_all(['td', 'th'])
        if len(row_cells) == 2:
            for c in list(row_cells[1].children):
                c.extract()
            p = soup.new_tag('p')
            p.string = _score_mark(scores.get(SCORE_KEYS[i], 0))
            row_cells[1].append(p)
        next_row = next_row.find_next_sibling('tr')


def _build_ticket_block(soup: BeautifulSoup, ticket: dict, seq_num: int,
                         include_brd: bool, add_cycle_cell: bool = True) -> list[Tag]:
    """6행 티켓 블록 생성 (rowspan 포함)."""
    scores = ticket.get('scores', {})
    brd_text = _count_o(scores) if include_brd else ''

    def td(text, rowspan=1):
        cell = soup.new_tag('td')
        if rowspan > 1:
            cell['rowspan'] = str(rowspan)
        p = soup.new_tag('p')
        p.string = str(text)
        cell.append(p)
        return cell

    rows = []
    tr1 = soup.new_tag('tr')
    tr1.append(td(seq_num, rowspan=6))                                     # #
    if add_cycle_cell:
        tr1.append(td(cycle_label(ticket.get('cycle_number', 0)), rowspan=6))  # Cycle
    tr1.append(td(ticket.get('key', ''), rowspan=6))                       # Key
    tr1.append(td(ticket.get('summary', ''), rowspan=6))                   # Summary
    tr1.append(td(ticket.get('reporter', ''), rowspan=6))                  # Reporter
    tr1.append(td(ticket.get('created', ''), rowspan=6))                   # Created
    tr1.append(td(ticket.get('due_date', ''), rowspan=6))                  # Due date

    content_td = soup.new_tag('td')
    content_td['rowspan'] = '6'
    _fill_content_cell(content_td, ticket, soup)
    tr1.append(content_td)

    tr1.append(td(SCORE_LABELS[0]))                                        # 시급성 레이블
    tr1.append(td(_score_mark(scores.get(SCORE_KEYS[0], 0))))              # 시급성 O/X
    tr1.append(td(str(ticket.get('priority_score', '')), rowspan=6))       # Priority
    tr1.append(td(brd_text, rowspan=6))                                    # O 개수
    rows.append(tr1)

    for i in range(1, 6):
        tr = soup.new_tag('tr')
        tr.append(td(SCORE_LABELS[i]))
        tr.append(td(_score_mark(scores.get(SCORE_KEYS[i], 0))))
        rows.append(tr)

    return rows


def _ensure_section(soup: BeautifulSoup, section_label: str) -> Tag:
    table = _find_section_table(soup, section_label)
    if table:
        return table

    table = soup.new_tag('table')
    tbody = soup.new_tag('tbody')

    tr_title = soup.new_tag('tr')
    td_title = soup.new_tag('td')
    td_title['colspan'] = '12'
    p = soup.new_tag('p')
    p.string = section_label
    td_title.append(p)
    tr_title.append(td_title)
    tbody.append(tr_title)

    headers = ['#', 'Cycle', 'Key', 'Ticket Summary', 'Reporter',
               'Created', 'Due date', '내용', '항목 분포', '', 'Priority 점수', 'BRD 승인 (O 수)']
    tr_head = soup.new_tag('tr')
    for i, h in enumerate(headers):
        th = soup.new_tag('th')
        if i == 8:
            th['colspan'] = '2'
        p = soup.new_tag('p')
        p.string = h
        th.append(p)
        tr_head.append(th)
        if i == 8:
            continue
    tbody.append(tr_head)

    table.append(tbody)
    h3 = soup.new_tag('h3')
    h3.string = section_label
    soup.append(h3)
    soup.append(table)
    return table


def _get_cycle_cell(table: Tag) -> Tag | None:
    """표에서 Cycle 셀 반환 (인덱스1, rowspan > 1)."""
    for row in table.find_all('tr')[2:]:
        cells = row.find_all(['td', 'th'])
        if len(cells) > 10 and int(cells[1].get('rowspan', 1)) > 1:
            return cells[1]
    return None


def update(tickets_with_analysis: list[dict], client: ConfluenceClient | None = None):
    if client is None:
        client = ConfluenceClient()

    page = client.find_page("doc1")
    page_id = page["id"]
    html, version, title = client.get_page_storage(page_id)
    soup = BeautifulSoup(html, 'html.parser')

    pre_brd  = [t for t in tickets_with_analysis if t.get('brd_approval') == 'Pre-BRD']
    post_brd = [t for t in tickets_with_analysis if t.get('brd_approval') != 'Pre-BRD']

    for section_label, tickets, include_brd in [
        ("BRD 프로세스 적용 이전 (Pre-BRD)", pre_brd, False),
        ("BRD 프로세스 적용 이후", post_brd, True),
    ]:
        table = _ensure_section(soup, section_label)
        existing_keys = _get_existing_keys(table)

        new_tickets     = [t for t in tickets if t.get('key', '') not in existing_keys]
        update_tickets  = [t for t in tickets if t.get('key', '') in existing_keys]

        for t in update_tickets:
            _update_ticket_row(existing_keys[t['key']], t, soup)

        if new_tickets:
            tbody = table.find('tbody') or table
            all_data_rows = [r for r in table.find_all('tr')
                             if any(int(c.get('rowspan', 1)) > 1 for c in r.find_all(['td', 'th']))]
            seq_start = len(all_data_rows) + 1

            cycle_cell = _get_cycle_cell(table)
            if cycle_cell:
                current_rowspan = int(cycle_cell.get('rowspan', 1))
                cycle_cell['rowspan'] = str(current_rowspan + len(new_tickets) * 6)

            for i, t in enumerate(new_tickets):
                # Cycle 셀: 기존 Cycle 셀 없을 때 첫 티켓에만 추가
                add_cycle = (cycle_cell is None and i == 0)
                rows = _build_ticket_block(soup, t, seq_start + i, include_brd,
                                           add_cycle_cell=add_cycle)
                for row in rows:
                    tbody.append(row)

    client.update_page(page_id, title, str(soup), version, "Doc1 Smart Update")
    print(f"[Doc1] 완료  Pre-BRD: {len(pre_brd)}건 / Post-BRD: {len(post_brd)}건")
