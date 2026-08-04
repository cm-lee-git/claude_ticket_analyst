"""
Document 1: KKR OneApp 주간 보고 (AI 생성) — Full Rebuild Updater
- 매 실행마다 Pre-BRD / Post-BRD를 단일 테이블로 완전히 재빌드
- Pre-BRD : cycle_number == 0인 티켓, created 오름차순
- Post-BRD: cycle_number >= 1인 티켓, cycle 오름차순 → created 오름차순
업데이트 주기: 매주 월요일 10:00
"""
from datetime import datetime
from bs4 import BeautifulSoup, Tag
from confluence_client import ConfluenceClient
from config import DOC_PAGE_IDS
from cycle import cycle_label

SCORE_LABELS = [
    "시급성", "사업 성과 기여", "고객 경험 영향도",
    "운영 효율화", "글로벌 파급 범위", "플랫폼 운영 전략 연계도",
]
SCORE_KEYS = [
    "urgency", "business_performance", "customer_experience",
    "operational_efficiency", "global_reach", "platform_strategy",
]
BRD_DISPLAY = {
    "Approved": "승인",
    "Pending":  "보류",
    "Rejected": "반려",
    "Pre-BRD":  "",
}

TABLE_TITLE  = "New/Improvement"
SECTION_PRE  = "BRD 프로세스 적용 이전 (Pre-BRD)"
SECTION_POST = "BRD 프로세스 적용 이후"
TOTAL_COLS   = 12

# 참조 문서(71139380)의 New/Improvement 표 열 너비 (px)
COL_WIDTHS = [51, 70, 182, 242, 93, 100, 98, 475, 147, 129, 105, 107]


def _score_mark(value) -> str:
    try:
        return 'O' if float(value) > 0 else 'X'
    except (ValueError, TypeError):
        return 'X'


def _count_o(scores: dict) -> str:
    """Priority 점수 = 시급성 제외 5개 항목 중 O 개수."""
    keys = SCORE_KEYS[1:]  # urgency 제외
    return str(sum(1 for k in keys if float(scores.get(k, 0)) > 0))


def _td(soup: BeautifulSoup, text, rowspan: int = 1) -> Tag:
    cell = soup.new_tag('td', style="padding: 14px 10px; line-height: 1.6;")
    if rowspan > 1:
        cell['rowspan'] = str(rowspan)
    p = soup.new_tag('p')
    p.string = str(text)
    cell.append(p)
    return cell


def _fill_content_cell(cell: Tag, ticket: dict, soup: BeautifulSoup):
    """내용 셀: <헤더> + 불렛 리스트 형식으로 채움."""
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
        if not content:
            continue

        # 헤더 줄
        p_label = soup.new_tag('p')
        strong = soup.new_tag('strong')
        strong.string = f'<{label}>'
        p_label.append(strong)
        cell.append(p_label)

        # 불렛 리스트
        ul = soup.new_tag('ul')
        if isinstance(content, list):
            items = [str(x).strip() for x in content if str(x).strip()]
        else:
            items = [line.strip() for line in str(content).split('\n') if line.strip()]
            if not items:
                items = [str(content).strip()]
        for item in items:
            li = soup.new_tag('li')
            li.string = item
            ul.append(li)
        cell.append(ul)


def _section_row(soup: BeautifulSoup, text: str, colour: str = "") -> Tag:
    """섹션 구분 행 (colspan 전체, 굵게, 선택적 배경색)."""
    tr = soup.new_tag('tr')
    td = soup.new_tag('td')
    td['colspan'] = str(TOTAL_COLS)
    if colour:
        td['data-highlight-colour'] = colour
    p = soup.new_tag('p')
    strong = soup.new_tag('strong')
    strong.string = text
    p.append(strong)
    td.append(p)
    tr.append(td)
    return tr


def _header_row(soup: BeautifulSoup) -> Tag:
    """컬럼 헤더 행."""
    col_specs = [
        ('#', 1), ('Cycle', 1), ('Key', 1), ('Ticket Summary', 1),
        ('Reporter', 1), ('Created', 1), ('Due date', 1),
        ('내용', 1), ('항목 분포', 2), ('Priority 점수', 1), ('BRD 승인 여부', 1),
    ]
    tr = soup.new_tag('tr')
    for text, colspan in col_specs:
        th = soup.new_tag('th', style="padding: 14px 10px;")
        if colspan > 1:
            th['colspan'] = str(colspan)
        p = soup.new_tag('p')
        p.string = text
        th.append(p)
        tr.append(th)
    return tr


def _build_ticket_block(soup: BeautifulSoup, ticket: dict,
                         seq_num: int, include_brd: bool) -> list[Tag]:
    """6행 티켓 블록 생성.
    - Priority 점수: 항상 표시 (O 개수)
    - BRD 승인 여부: include_brd=True일 때만 표시 (Pre-BRD 티켓은 공란)
    """
    scores = ticket.get('scores', {})
    priority_text = _count_o(scores)
    brd_text = BRD_DISPLAY.get(ticket.get('brd_approval', ''), '') if include_brd else ''

    rows = []
    tr1 = soup.new_tag('tr')
    tr1.append(_td(soup, seq_num, rowspan=6))
    tr1.append(_td(soup, cycle_label(ticket.get('cycle_number', 0)), rowspan=6))
    tr1.append(_td(soup, ticket.get('key', ''), rowspan=6))
    tr1.append(_td(soup, ticket.get('summary', ''), rowspan=6))
    tr1.append(_td(soup, ticket.get('reporter', ''), rowspan=6))
    tr1.append(_td(soup, ticket.get('created', ''), rowspan=6))
    tr1.append(_td(soup, ticket.get('due_date', ''), rowspan=6))

    content_td = soup.new_tag('td')
    content_td['rowspan'] = '6'
    _fill_content_cell(content_td, ticket, soup)
    tr1.append(content_td)

    tr1.append(_td(soup, SCORE_LABELS[0]))
    tr1.append(_td(soup, _score_mark(scores.get(SCORE_KEYS[0], 0))))
    tr1.append(_td(soup, priority_text, rowspan=6))
    tr1.append(_td(soup, brd_text, rowspan=6))
    rows.append(tr1)

    for i in range(1, 6):
        tr = soup.new_tag('tr')
        tr.append(_td(soup, SCORE_LABELS[i]))
        tr.append(_td(soup, _score_mark(scores.get(SCORE_KEYS[i], 0))))
        rows.append(tr)

    return rows


def _build_full_table(soup: BeautifulSoup,
                       pre_brd: list[dict], post_brd: list[dict]) -> Tag:
    """Pre-BRD + Post-BRD를 단일 테이블로 생성. 번호는 연속."""
    table = soup.new_tag('table')

    # 열 너비 설정 (참조 문서 기준)
    colgroup = soup.new_tag('colgroup')
    for w in COL_WIDTHS:
        col = soup.new_tag('col', style=f"width: {w}.0px;")
        colgroup.append(col)
    table.append(colgroup)

    tbody = soup.new_tag('tbody')

    # 테이블 타이틀 행
    tr_title = soup.new_tag('tr')
    td_title = soup.new_tag('td')
    td_title['colspan'] = str(TOTAL_COLS)
    p = soup.new_tag('p')
    strong = soup.new_tag('strong')
    strong.string = TABLE_TITLE
    p.append(strong)
    td_title.append(p)
    tr_title.append(td_title)
    tbody.append(tr_title)

    # Pre-BRD 섹션 (옅은 빨간색)
    tbody.append(_section_row(soup, SECTION_PRE, colour="#ffebe6"))
    tbody.append(_header_row(soup))
    for i, ticket in enumerate(pre_brd):
        for row in _build_ticket_block(soup, ticket, i + 1, include_brd=False):
            tbody.append(row)

    # Post-BRD 섹션 (옅은 파란색)
    tbody.append(_section_row(soup, SECTION_POST, colour="#e6fcff"))
    for i, ticket in enumerate(post_brd):
        for row in _build_ticket_block(
                soup, ticket, len(pre_brd) + i + 1, include_brd=True):
            tbody.append(row)

    table.append(tbody)
    return table


def update(tickets_with_analysis: list[dict], client: ConfluenceClient | None = None):
    if client is None:
        client = ConfluenceClient()

    # Pre-BRD: cycle_number == 0, created 오름차순
    pre_brd = sorted(
        [t for t in tickets_with_analysis if t.get('cycle_number', 0) == 0],
        key=lambda t: t.get('created', '')
    )
    # Post-BRD: cycle_number >= 1, cycle 오름차순 → created 오름차순
    post_brd = sorted(
        [t for t in tickets_with_analysis if t.get('cycle_number', 0) > 0],
        key=lambda t: (t.get('cycle_number', 0), t.get('created', ''))
    )

    # 새 페이지 콘텐츠 빌드
    soup = BeautifulSoup("", 'html.parser')
    new_table = _build_full_table(soup, pre_brd, post_brd)
    soup.append(new_table)

    # 타임스탬프 제목으로 새 페이지 생성 (AI 생성 폴더 하위)
    timestamp = datetime.now().strftime("%m-%d %H:%M")
    title = f"{timestamp} KKR OneApp 주간 보고 (AI 생성)"
    parent_id = DOC_PAGE_IDS["doc1"]

    result = client.create_page(parent_id, title, str(soup))
    new_id = result.get("id", "")
    print(f"[Doc1] 완료  Pre-BRD: {len(pre_brd)}건 / Post-BRD: {len(post_brd)}건")
    print(f"[Doc1] 새 페이지: {title}  (id={new_id})")
