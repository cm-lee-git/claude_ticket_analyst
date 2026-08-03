"""
Document 1: KKR OneApp 주간 보고 (AI 생성) — Full Rebuild Updater
- 매 실행마다 Pre-BRD / Post-BRD 표를 완전히 재빌드
- 각 티켓마다 고유 Cycle 셀(rowspan=6) 보유
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


def _score_mark(value) -> str:
    try:
        return 'O' if float(value) > 0 else 'X'
    except (ValueError, TypeError):
        return 'X'


def _count_o(scores: dict) -> str:
    """Priority 점수 = 시급성 제외 5개 항목 O 개수."""
    keys = SCORE_KEYS[1:]   # urgency 제외
    return str(sum(1 for k in keys if float(scores.get(k, 0)) > 0))


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


def _build_ticket_block(soup: BeautifulSoup, ticket: dict,
                         seq_num: int, include_brd: bool) -> list[Tag]:
    """6행 티켓 블록 생성. Cycle 셀은 항상 각 티켓에 포함(rowspan=6)."""
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
    tr1.append(td(seq_num, rowspan=6))                                          # #
    tr1.append(td(cycle_label(ticket.get('cycle_number', 0)), rowspan=6))       # Cycle
    tr1.append(td(ticket.get('key', ''), rowspan=6))                            # Key
    tr1.append(td(ticket.get('summary', ''), rowspan=6))                        # Ticket Summary
    tr1.append(td(ticket.get('reporter', ''), rowspan=6))                       # Reporter
    tr1.append(td(ticket.get('created', ''), rowspan=6))                        # Created
    tr1.append(td(ticket.get('due_date', ''), rowspan=6))                       # Due date

    content_td = soup.new_tag('td')
    content_td['rowspan'] = '6'
    _fill_content_cell(content_td, ticket, soup)
    tr1.append(content_td)                                                       # 내용

    tr1.append(td(SCORE_LABELS[0]))                                              # 항목 레이블
    tr1.append(td(_score_mark(scores.get(SCORE_KEYS[0], 0))))                   # 항목 O/X
    tr1.append(td(brd_text, rowspan=6))                                          # O 개수
    rows.append(tr1)

    for i in range(1, 6):
        tr = soup.new_tag('tr')
        tr.append(td(SCORE_LABELS[i]))
        tr.append(td(_score_mark(scores.get(SCORE_KEYS[i], 0))))
        rows.append(tr)

    return rows


def _build_section_table(soup: BeautifulSoup, section_label: str,
                          tickets: list[dict], include_brd: bool) -> Tag:
    """섹션 표를 처음부터 완전히 생성."""
    table = soup.new_tag('table')
    tbody = soup.new_tag('tbody')

    # 타이틀행
    tr_title = soup.new_tag('tr')
    td_title = soup.new_tag('td')
    td_title['colspan'] = '11'
    p = soup.new_tag('p')
    p.string = section_label
    td_title.append(p)
    tr_title.append(td_title)
    tbody.append(tr_title)

    # 헤더행
    col_specs = [
        ('#', 1), ('Cycle', 1), ('Key', 1), ('Ticket Summary', 1),
        ('Reporter', 1), ('Created', 1), ('Due date', 1),
        ('내용', 1), ('항목 분포', 2), ('BRD 승인 (O 수)', 1),
    ]
    tr_head = soup.new_tag('tr')
    for text, colspan in col_specs:
        th = soup.new_tag('th')
        if colspan > 1:
            th['colspan'] = str(colspan)
        p = soup.new_tag('p')
        p.string = text
        th.append(p)
        tr_head.append(th)
    tbody.append(tr_head)

    # 티켓 데이터행
    for i, ticket in enumerate(tickets):
        rows = _build_ticket_block(soup, ticket, i + 1, include_brd)
        for row in rows:
            tbody.append(row)

    table.append(tbody)
    return table


def _replace_or_create_section(soup: BeautifulSoup, section_label: str,
                                 tickets: list[dict], include_brd: bool):
    """기존 섹션 표를 교체하거나 없으면 새로 추가."""
    # 기존 표 탐색 (타이틀행 텍스트 기준)
    old_table = None
    for table in soup.find_all('table'):
        first_row = table.find('tr')
        if first_row and section_label in first_row.get_text():
            old_table = table
            break

    new_table = _build_section_table(soup, section_label, tickets, include_brd)

    if old_table:
        old_table.replace_with(new_table)
    else:
        h3 = soup.new_tag('h3')
        h3.string = section_label
        soup.append(h3)
        soup.append(new_table)


def update(tickets_with_analysis: list[dict], client: ConfluenceClient | None = None):
    if client is None:
        client = ConfluenceClient()

    page = client.find_page("doc1")
    page_id = page["id"]
    html, version, title = client.get_page_storage(page_id)
    soup = BeautifulSoup(html, 'html.parser')

    pre_brd  = [t for t in tickets_with_analysis if t.get('brd_approval') == 'Pre-BRD']
    post_brd = [t for t in tickets_with_analysis if t.get('brd_approval') != 'Pre-BRD']

    _replace_or_create_section(soup, "BRD 프로세스 적용 이전 (Pre-BRD)", pre_brd,  False)
    _replace_or_create_section(soup, "BRD 프로세스 적용 이후",           post_brd, True)

    client.update_page(page_id, title, str(soup), version, "Doc1 Full Rebuild")
    print(f"[Doc1] 완료  Pre-BRD: {len(pre_brd)}건 / Post-BRD: {len(post_brd)}건")
