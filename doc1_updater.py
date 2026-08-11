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
    "보류":     "보류",
    "반려":     "반려",
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


JIRA_BROWSE = "https://hmg.atlassian.net/browse"
import re as _re
_TICKET_PATTERN = _re.compile(r'\b(KCCIVOC|KEUVOCOP|CCIPRJ)-\d+\b')


def _linkify(soup: BeautifulSoup, text: str) -> list:
    """텍스트 내 Jira 티켓 키 패턴을 하이퍼링크로 변환, BeautifulSoup 노드 리스트 반환."""
    parts = []
    last = 0
    for m in _TICKET_PATTERN.finditer(text):
        if m.start() > last:
            parts.append(soup.new_string(text[last:m.start()]))
        a = soup.new_tag('a', href=f"{JIRA_BROWSE}/{m.group()}")
        a.string = m.group()
        parts.append(a)
        last = m.end()
    if last < len(text):
        parts.append(soup.new_string(text[last:]))
    return parts or [soup.new_string(text)]


def _td(soup: BeautifulSoup, text, rowspan: int = 1) -> Tag:
    cell = soup.new_tag('td', style="padding: 14px 10px; line-height: 1.6;")
    if rowspan > 1:
        cell['rowspan'] = str(rowspan)
    p = soup.new_tag('p')
    p.string = str(text)
    cell.append(p)
    return cell


def _td_link(soup: BeautifulSoup, key: str, rowspan: int = 1) -> Tag:
    """Key 셀 — Jira 티켓 URL 하이퍼링크."""
    cell = soup.new_tag('td', style="padding: 14px 10px; line-height: 1.6;")
    if rowspan > 1:
        cell['rowspan'] = str(rowspan)
    p = soup.new_tag('p')
    a = soup.new_tag('a', href=f"{JIRA_BROWSE}/{key}")
    a.string = key
    p.append(a)
    cell.append(p)
    return cell


def _fill_content_cell(cell: Tag, ticket: dict, soup: BeautifulSoup):
    """내용 셀: <헤더> + 불렛 리스트 형식으로 채움."""
    for child in list(cell.children):
        child.extract()

    feature_label = ticket.get('feature_label') or '기존 기능 개선'
    sections = [
        # Status: 현재 처리 상태 (있을 경우 Summary 위에 배치)
        ('Status',       ticket.get('status_info', '')),
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
            for node in _linkify(soup, item):
                li.append(node)
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
    if not include_brd:
        brd_text = '-'
    elif ticket.get('rejection_code'):
        brd_text = '반려'
    elif ticket.get('hold_code'):
        brd_text = '보류'
    else:
        brd_text = BRD_DISPLAY.get(ticket.get('brd_approval', ''), '')

    rows = []
    tr1 = soup.new_tag('tr')
    tr1.append(_td(soup, seq_num, rowspan=6))
    tr1.append(_td(soup, cycle_label(ticket.get('cycle_number', 0)), rowspan=6))
    tr1.append(_td_link(soup, ticket.get('key', ''), rowspan=6))
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


def _make_table(soup: BeautifulSoup) -> tuple[Tag, Tag]:
    """colgroup이 있는 빈 table + tbody 반환."""
    table = soup.new_tag('table')
    colgroup = soup.new_tag('colgroup')
    for w in COL_WIDTHS:
        col = soup.new_tag('col', style=f"width: {w}.0px;")
        colgroup.append(col)
    table.append(colgroup)
    tbody = soup.new_tag('tbody')
    table.append(tbody)
    return table, tbody


def _build_pre_brd_table(soup: BeautifulSoup, pre_brd: list[dict]) -> Tag:
    """Pre-BRD 전용 표."""
    table, tbody = _make_table(soup)
    tbody.append(_section_row(soup, SECTION_PRE, colour="#ffebe6"))
    tbody.append(_header_row(soup))
    for i, ticket in enumerate(pre_brd):
        for row in _build_ticket_block(soup, ticket, i + 1, include_brd=False):
            tbody.append(row)
    return table


def _build_post_brd_table(soup: BeautifulSoup, post_brd: list[dict],
                           offset: int) -> Tag:
    """BRD 이후 프로세스 전용 표 (섹션 행 + 헤더 행 포함)."""
    table, tbody = _make_table(soup)
    tbody.append(_section_row(soup, SECTION_POST, colour="#e6fcff"))
    tbody.append(_header_row(soup))
    for i, ticket in enumerate(post_brd):
        for row in _build_ticket_block(
                soup, ticket, offset + i + 1, include_brd=True):
            tbody.append(row)
    return table


def _count_tickets_in_tbody(tbody: Tag) -> int:
    """tbody에서 티켓 수 카운트: 첫 번째 셀이 rowspan=6인 행 수."""
    count = 0
    for tr in tbody.find_all('tr'):
        first = tr.find(['td', 'th'])
        if first and first.get('rowspan') == '6':
            count += 1
    return count


def append_new_tickets(tickets_with_analysis: list[dict],
                       client: ConfluenceClient | None = None):
    """화~금: 당일 신규 티켓만 기존 최신 doc1 페이지에 추가."""
    if client is None:
        client = ConfluenceClient()

    # Doc1는 KR 권역 티켓만 포함
    tickets_with_analysis = [t for t in tickets_with_analysis if t.get("region") == "KR"]
    if not tickets_with_analysis:
        print("[Doc1-Daily] 신규 KR 티켓 없음 → 종료")
        return

    # 최신 doc1 페이지 찾기 (제목 내림차순 = 가장 최근 월요일 페이지)
    children = client.get_child_pages(DOC_PAGE_IDS["doc1"])
    if not children:
        print("[Doc1-Daily] 기존 페이지 없음 → 종료")
        return
    latest = sorted(children, key=lambda p: p["title"], reverse=True)[0]
    page_id = latest["id"]
    print(f"[Doc1-Daily] 대상 페이지: {latest['title']} (id={page_id})")

    html, version, title = client.get_page_storage(page_id)
    soup = BeautifulSoup(html, 'html.parser')

    tables = soup.find_all('table')
    if len(tables) < 2:
        print("[Doc1-Daily] 표 구조 이상 (2개 미만) → 종료")
        return

    pre_tbody  = tables[0].find('tbody')
    post_tbody = tables[1].find('tbody')

    pre_existing  = _count_tickets_in_tbody(pre_tbody)
    post_existing = _count_tickets_in_tbody(post_tbody)

    # 신규 티켓 분류
    new_pre = sorted(
        [t for t in tickets_with_analysis if t.get('cycle_number', 0) == 0],
        key=lambda t: t.get('created', '')
    )
    new_post = sorted(
        [t for t in tickets_with_analysis if t.get('cycle_number', 0) > 0],
        key=lambda t: (t.get('cycle_number', 0), t.get('created', ''))
    )

    # Pre-BRD 표에 추가
    for i, ticket in enumerate(new_pre):
        for row in _build_ticket_block(soup, ticket, pre_existing + i + 1, include_brd=False):
            pre_tbody.append(row)

    # Post-BRD 표에 추가
    for i, ticket in enumerate(new_post):
        for row in _build_ticket_block(soup, ticket, post_existing + i + 1, include_brd=True):
            post_tbody.append(row)

    client.update_page(page_id, title, str(soup), version,
                       message=f"Daily: {len(new_pre)}건 Pre-BRD, {len(new_post)}건 Post-BRD 추가")
    print(f"[Doc1-Daily] 완료  Pre-BRD+{len(new_pre)}건 / Post-BRD+{len(new_post)}건")
    print(f"[Doc1-Daily] 페이지 업데이트: {title} (id={page_id})")


def update(tickets_with_analysis: list[dict], client: ConfluenceClient | None = None):
    if client is None:
        client = ConfluenceClient()

    # Doc1는 KR 권역 티켓만 포함
    kr_tickets = [t for t in tickets_with_analysis if t.get("region") == "KR"]

    # Pre-BRD: cycle_number == 0, created 오름차순
    pre_brd = sorted(
        [t for t in kr_tickets if t.get('cycle_number', 0) == 0],
        key=lambda t: t.get('created', '')
    )
    # Post-BRD: cycle_number >= 1, cycle 오름차순 → created 오름차순
    post_brd = sorted(
        [t for t in kr_tickets if t.get('cycle_number', 0) > 0],
        key=lambda t: (t.get('cycle_number', 0), t.get('created', ''))
    )

    # 새 페이지 콘텐츠 빌드
    soup = BeautifulSoup("", 'html.parser')

    # 목차
    toc = BeautifulSoup(
        '<ac:structured-macro ac:name="toc" ac:schema-version="1">'
        '<ac:parameter ac:name="style">none</ac:parameter>'
        '</ac:structured-macro>', 'html.parser')
    soup.append(toc)

    # h1: New/Improvement (표 바깥 헤딩)
    h1 = soup.new_tag('h1')
    h1.string = TABLE_TITLE
    soup.append(h1)

    # h2: Pre-BRD 섹션 제목 (목차 연결용)
    h2_pre = soup.new_tag('h2')
    h2_pre.string = SECTION_PRE
    soup.append(h2_pre)

    # 표 1: Pre-BRD
    soup.append(_build_pre_brd_table(soup, pre_brd))

    # h2: Post-BRD 섹션 제목 (목차 연결용)
    h2_post = soup.new_tag('h2')
    h2_post.string = SECTION_POST
    soup.append(h2_post)

    # 표 2: BRD 이후 프로세스 (별도 표로 시작)
    soup.append(_build_post_brd_table(soup, post_brd, offset=len(pre_brd)))

    # 타임스탬프 제목으로 새 페이지 생성 (AI 생성 폴더 하위)
    timestamp = datetime.now().strftime("%m-%d %H:%M")
    title = f"{timestamp} KKR OneApp 주간 보고 (AI 생성)"
    parent_id = DOC_PAGE_IDS["doc1"]

    result = client.create_page(parent_id, title, str(soup))
    new_id = result.get("id", "")
    print(f"[Doc1] 완료  Pre-BRD: {len(pre_brd)}건 / Post-BRD: {len(post_brd)}건")
    print(f"[Doc1] 새 페이지: {title}  (id={new_id})")
