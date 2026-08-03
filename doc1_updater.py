"""
Document 1: KKR OneApp 주간 보고 (AI 생성) — Smart Updater
- 기존 티켓: Key로 탐색 후 셀 값 업데이트
- 신규 티켓: 6행 rowspan 블록 추가
- Pre-BRD / Post-BRD 섹션 구분
업데이트 주기: 매주 월요일 10:00
"""
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


def _fill_content_cell(cell: Tag, ticket: dict, soup: BeautifulSoup):
    """내용 셀을 <Summary>/<배경>/<문제>/<기능> 형식으로 채움."""
    for child in list(cell.children):
        child.extract()

    feature_label = ticket.get('feature_label') or '기존 기능 개선'
    sections = [
        ('Summary',      ticket.get('summary_ko') or ticket.get('summary', '')),
        ('배경',         ticket.get('background', '')),
        ('문제',         ticket.get('problem', '')),
        (feature_label,  ticket.get('feature', '')),
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


def _find_ticket_key_in_row(row: Tag) -> str:
    """행의 Key 컬럼(인덱스2) 텍스트 반환."""
    cells = row.find_all(['td', 'th'])
    if len(cells) > 2:
        return cells[2].get_text(strip=True)
    return ""


def _find_section_table(soup: BeautifulSoup, section_text: str) -> Tag | None:
    """section_text가 포함된 타이틀행을 가진 표 반환."""
    for table in soup.find_all('table'):
        first_row = table.find('tr')
        if first_row and section_text in first_row.get_text():
            return table
    return None


def _get_existing_keys(table: Tag) -> dict[str, Tag]:
    """표에서 Key → 첫 번째 데이터행 매핑 반환."""
    keys = {}
    rows = table.find_all('tr')
    for row in rows:
        cells = row.find_all(['td', 'th'])
        # Key 컬럼: rowspan 있는 셀이 많은 행 = 첫 번째 티켓 행
        has_rowspan = any(int(c.get('rowspan', 1)) > 1 for c in cells)
        if has_rowspan and len(cells) > 2:
            key_text = cells[2].get_text(strip=True)
            if key_text and key_text not in keys:
                keys[key_text] = row
    return keys


def _update_ticket_row(first_row: Tag, ticket: dict, soup: BeautifulSoup):
    """기존 티켓의 첫 번째 행 + 이후 5개 점수 행을 업데이트."""
    cells = first_row.find_all(['td', 'th'])
    scores = ticket.get('scores', {})

    # rowspan 셀 업데이트 (인덱스: 3=Summary, 4=Reporter, 5=Created, 6=Due, 7=내용, 10=Priority, 11=BRD)
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
    # 내용 셀 업데이트
    if 7 < len(cells):
        _fill_content_cell(cells[7], ticket, soup)
    set_cell(9, str(scores.get(SCORE_KEYS[0], '')))  # 시급성 점수
    set_cell(10, str(ticket.get('priority_score', '')))
    set_cell(11, ticket.get('brd_approval', '') if ticket.get('brd_approval') != 'Pre-BRD' else '')

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
            p.string = str(scores.get(SCORE_KEYS[i], ''))
            row_cells[1].append(p)
        next_row = next_row.find_next_sibling('tr')


def _build_ticket_block(soup: BeautifulSoup, ticket: dict, seq_num: int,
                         cycle_rowspan: int, include_brd: bool) -> list[Tag]:
    """6행 티켓 블록 생성 (rowspan 포함)."""
    scores = ticket.get('scores', {})
    brd_text = ticket.get('brd_approval', '') if include_brd else ''

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

    # Row 1: 주요 데이터 + 시급성
    tr1 = soup.new_tag('tr')
    tr1.append(td(seq_num, rowspan=6))                          # #
    tr1.append(td(cycle_label(ticket.get('cycle_number', 0)), rowspan=cycle_rowspan))  # Cycle (첫 티켓만 포함)
    tr1.append(td(ticket.get('key', ''), rowspan=6))            # Key
    tr1.append(td(ticket.get('summary', ''), rowspan=6))        # Summary
    tr1.append(td(ticket.get('reporter', ''), rowspan=6))       # Reporter
    tr1.append(td(ticket.get('created', ''), rowspan=6))        # Created
    tr1.append(td(ticket.get('due_date', ''), rowspan=6))       # Due date
    # 내용 셀
    content_td = soup.new_tag('td')
    content_td['rowspan'] = '6'
    _fill_content_cell(content_td, ticket, soup)
    tr1.append(content_td)
    tr1.append(td(SCORE_LABELS[0]))                             # 시급성 레이블
    tr1.append(td(scores.get(SCORE_KEYS[0], '')))               # 시급성 점수
    tr1.append(td(ticket.get('priority_score', ''), rowspan=6)) # Priority
    tr1.append(td(brd_text, rowspan=6))                         # BRD승인
    rows.append(tr1)

    # Rows 2~6: 나머지 스코어링
    for i in range(1, 6):
        tr = soup.new_tag('tr')
        tr.append(td(SCORE_LABELS[i]))
        tr.append(td(scores.get(SCORE_KEYS[i], '')))
        rows.append(tr)

    return rows


def _ensure_section(soup: BeautifulSoup, section_label: str) -> Tag:
    """섹션이 없으면 새 표 생성, 있으면 해당 표 반환."""
    table = _find_section_table(soup, section_label)
    if table:
        return table

    # 새 표 생성 (타이틀행 + 헤더행)
    table = soup.new_tag('table')
    tbody = soup.new_tag('tbody')

    # 타이틀행
    tr_title = soup.new_tag('tr')
    td_title = soup.new_tag('td')
    td_title['colspan'] = '12'
    p = soup.new_tag('p')
    p.string = section_label
    td_title.append(p)
    tr_title.append(td_title)
    tbody.append(tr_title)

    # 헤더행
    headers = ['#', 'Cycle', 'Key', 'Ticket Summary', 'Reporter',
               'Created', 'Due date', '내용', '항목 분포', '', 'Priority 점수', 'BRD 승인 여부']
    tr_head = soup.new_tag('tr')
    for i, h in enumerate(headers):
        th = soup.new_tag('th')
        if i == 8:
            th['colspan'] = '2'
        p = soup.new_tag('p')
        p.string = h
        th.append(p)
        tr_head.append(th)
        if i == 8:  # colspan=2이므로 다음 빈 헤더 스킵
            continue
    tbody.append(tr_head)

    table.append(tbody)
    soup.append(soup.new_tag('h3'))
    soup.find('h3').string = section_label
    soup.append(table)
    return table


def _get_cycle_cell(table: Tag) -> Tag | None:
    """표에서 Cycle 컬럼 셀(인덱스1, rowspan 큰 것) 반환."""
    rows = table.find_all('tr')
    for row in rows[2:]:  # 타이틀행·헤더행 제외
        cells = row.find_all(['td', 'th'])
        if len(cells) > 10:  # 첫 번째 데이터 행
            if int(cells[1].get('rowspan', 1)) > 1:
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

        new_tickets = [t for t in tickets if t.get('key', '') not in existing_keys]
        update_tickets = [t for t in tickets if t.get('key', '') in existing_keys]

        # 기존 티켓 업데이트
        for t in update_tickets:
            _update_ticket_row(existing_keys[t['key']], t, soup)

        # 신규 티켓 추가
        if new_tickets:
            tbody = table.find('tbody') or table
            all_data_rows = [r for r in table.find_all('tr')
                            if any(int(c.get('rowspan',1)) > 1 for c in r.find_all(['td','th']))]
            seq_start = len(all_data_rows) + 1

            # Cycle 셀 rowspan 확장
            cycle_cell = _get_cycle_cell(table)
            current_rowspan = int(cycle_cell.get('rowspan', 1)) if cycle_cell else 0

            for i, t in enumerate(new_tickets):
                is_first = (i == 0 and cycle_cell is None)
                c_rowspan = (len(new_tickets) * 6) if is_first else 0
                if cycle_cell and i == 0:
                    cycle_cell['rowspan'] = str(current_rowspan + len(new_tickets) * 6)

                rows = _build_ticket_block(soup, t, seq_start + i,
                                           c_rowspan, include_brd)
                if i > 0:
                    rows[0].find('td', {'rowspan': str(c_rowspan)})  # Cycle 셀 제거
                    # 두 번째 티켓부터 Cycle 셀 없이 추가
                    cycle_td = rows[0].find_all('td')[1]
                    if int(cycle_td.get('rowspan', 1)) > 1:
                        cycle_td.decompose()

                for row in rows:
                    tbody.append(row)

    new_html = str(soup)
    client.update_page(page_id, title, new_html, version, "Doc1 Smart Update")
    print(f"[Doc1] 완료  Pre-BRD: {len(pre_brd)}건 / Post-BRD: {len(post_brd)}건")
