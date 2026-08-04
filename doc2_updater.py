"""
Document 2: 신규/개선 전체 현황 — 새 페이지 생성 방식
원본(71237682) 구조와 동일하게 생성:
  Section 0: 스크리닝 기준 (정적)
  Section 1: 전체 현황 + 회차별 트래킹 + 마감 히스토리 expand
  Section 2: KR 티켓 히스토리 (승인/보류/반려 × Pre-BRD/회차별 expand)
  Section 3: EU 티켓 히스토리
  Section 4: HQ GBCXD 및 타부문 티켓 히스토리
"""
from collections import defaultdict
from datetime import datetime

from confluence_client import ConfluenceClient
from config import DOC_PAGE_IDS
from cycle import cycle_label, get_cycle_bounds

# ── 상수 ────────────────────────────────────────────────────────
SCORE_LABELS = [
    "시급성", "사업 성과 기여", "고객 경험 영향도",
    "운영 효율화", "글로벌 파급 범위", "플랫폼 운영 전략 연계도",
]
SCORE_KEYS = [
    "urgency", "business_performance", "customer_experience",
    "operational_efficiency", "global_reach", "platform_strategy",
]

REGION_LABEL = {"KR": "RHQ KR", "EU": "RHQ EU", "HQ": "HQ GBCXD 및 타부문"}
APPROVAL_LABEL = {"Approved": "승인", "Pending": "보류", "Rejected": "반려", "Pre-BRD": "-"}

# 참조 문서(71237682) 기준 colgroup 너비
CW = {
    "section1_overall":   [107, 159, 133, 133, 133, 133],      # 6열: 전체현황
    "section1_tracking":  [122, 108, 87, 92, 71, 90, 85, 106,  # 19열: 트래킹
                           83, 98, 81, 92, 92, 106, 87, 83, 92, 92, 92],
    "kr_approved":        [104, 93, 101, 167, 93, 93, 93,       # 12열: KR 승인
                           291, 93, 93, 93, 104],
    "kr_pending":         [208, 110, 110, 110, 110, 110,        # 12열: KR 보류
                           110, 110, 110, 110, 110, 110],
    "kr_rejected":        [200, 132, 132, 135, 132, 132,        # 10열: KR 반려
                           132, 132, 159, 132],
    "eu_approved":        [198, 122, 122, 122, 122, 122,        # 11열: EU 승인
                           122, 122, 122, 122, 122],
    "eu_pending":         [198, 122, 122, 122, 122, 122,        # 11열: EU 보류
                           122, 122, 122, 122, 122],
    "eu_rejected":        [198, 122, 122, 122, 122, 122,        # 10열: EU 반려
                           122, 122, 122, 122],
    "history":            [122, 108, 87, 92, 71, 90, 85, 106,  # 13열: 마감 히스토리
                           83, 98, 81, 92, 92],
}


# ── HTML 빌더 헬퍼 ───────────────────────────────────────────────
def _colgroup(widths):
    cols = "".join(f'<col style="width: {w}.0px;"/>' for w in widths)
    return f"<colgroup>{cols}</colgroup>"


def _table(widths, rows_html):
    cg = _colgroup(widths) if widths else ""
    return f"<table>{cg}<tbody>{''.join(rows_html)}</tbody></table>"


def _th(*headers):
    return "<tr>" + "".join(f"<th><p>{h}</p></th>" for h in headers) + "</tr>"


def _th_span(cells):
    """cells: list of (text, rowspan, colspan)"""
    parts = []
    for text, rs, cs in cells:
        attrs = (f' rowspan="{rs}"' if rs > 1 else "") + (f' colspan="{cs}"' if cs > 1 else "")
        parts.append(f"<th{attrs}><p>{text}</p></th>")
    return "<tr>" + "".join(parts) + "</tr>"


def _td(*cells, style=""):
    st = f' style="{style}"' if style else ""
    return "<tr>" + "".join(f"<td{st}><p>{c}</p></td>" for c in cells) + "</tr>"


def _p(text):
    return f"<p>{text}</p>"


def _h2(text):
    return f"<h2>{text}</h2>"


def _h3(text):
    return f"<h3>{text}</h3>"


def _expand(title, content):
    return (
        f'<ac:structured-macro ac:name="expand">'
        f'<ac:parameter ac:name="title">{title}</ac:parameter>'
        f'<ac:rich-text-body>{content}</ac:rich-text-body>'
        f'</ac:structured-macro>'
    )


def _no_tickets():
    return _p("해당 티켓 없음")


def _score_mark(value):
    try:
        return "O" if float(value) > 0 else "X"
    except (ValueError, TypeError):
        return "X"


def _cycle_expand_title(cycle_n):
    start, end = get_cycle_bounds(cycle_n)
    return f"#{cycle_label(cycle_n)} ({start.strftime('%Y. %-m/%-d')}~{end.strftime('%-m/%-d')})"


def _cnt(tickets, region=None, approval=None):
    result = tickets
    if region:
        result = [t for t in result if t.get("region") == region]
    if approval:
        if isinstance(approval, list):
            result = [t for t in result if t.get("brd_approval") in approval]
        else:
            result = [t for t in result if t.get("brd_approval") == approval]
    return len(result)


def _get_all_cycles(tickets):
    return sorted({t.get("cycle_number", 0) for t in tickets if t.get("cycle_number", 0) > 0})


# ── 승인 티켓 테이블 (rowspan=6 스코어링, KR 12열 / EU·HQ 11열) ───
def _build_approved_table(tickets, widths, has_cycle_col, is_prebrd=False):
    if not tickets:
        return _no_tickets()

    last_col = "CCI 안건 상정 여부" if is_prebrd else "BRD 승인 여부"
    if has_cycle_col:
        header = _th("#", "회차", "Key", "Ticket Summary", "Reporter", "Created",
                     "Due date", "내용", "항목 분포", "Priority 점수", last_col)
    else:
        header = _th("#", "Key", "Ticket Summary", "Reporter", "Created",
                     "Due date", "내용", "항목 분포", "Priority Score", last_col)

    def td_rs(text, rs=6):
        return f'<td rowspan="{rs}"><p>{text}</p></td>'

    def _content_html(t):
        feature_label = t.get("feature_label") or "기존 기능 개선"
        parts = []
        for label, key in [("Summary", "summary_ko"), ("배경", "background"),
                            ("문제", "problem"), (feature_label, "feature")]:
            val = t.get(key) or (t.get("summary", "") if key == "summary_ko" else "")
            if val:
                lines = [line.strip() for line in val.split("\n") if line.strip()] or [val.strip()]
                bullets = "".join(f"<li>{line}</li>" for line in lines)
                parts.append(f"<p><strong>&lt;{label}&gt;</strong></p><ul>{bullets}</ul>")
        return "".join(parts)

    rows = [header]
    for seq, t in enumerate(tickets, 1):
        scores = t.get("scores", {})
        priority = str(sum(1 for k in SCORE_KEYS[1:] if float(scores.get(k, 0)) > 0))
        brd_val = "" if is_prebrd else APPROVAL_LABEL.get(t.get("brd_approval", ""), "")
        content_html = _content_html(t)
        cycle_col = f'<td rowspan="6"><p>{cycle_label(t.get("cycle_number", 0))}</p></td>' if has_cycle_col else ""

        # Row 1
        rows.append(
            f"<tr>"
            f'{td_rs(str(seq))}'
            f'{cycle_col}'
            f'{td_rs(t.get("key", ""))}'
            f'{td_rs(t.get("summary", ""))}'
            f'{td_rs(t.get("reporter", ""))}'
            f'{td_rs(t.get("created", ""))}'
            f'{td_rs(t.get("due_date", ""))}'
            f'<td rowspan="6">{content_html}</td>'
            f'<td><p>{SCORE_LABELS[0]}</p></td>'
            f'<td><p>{_score_mark(scores.get(SCORE_KEYS[0], 0))}</p></td>'
            f'{td_rs(priority)}'
            f'{td_rs(brd_val)}'
            f"</tr>"
        )
        # Rows 2-6
        for i in range(1, 6):
            rows.append(
                f"<tr>"
                f'<td><p>{SCORE_LABELS[i]}</p></td>'
                f'<td><p>{_score_mark(scores.get(SCORE_KEYS[i], 0))}</p></td>'
                f"</tr>"
            )

    return _table(widths, rows)


# ── 보류 티켓 테이블 (flat, KR 12열 / EU·HQ 11열) ───────────────
def _build_pending_table(tickets, widths, has_cycle_col):
    if not tickets:
        return _no_tickets()

    if has_cycle_col:
        header = _th("#", "회차", "Key", "Ticket Summary", "Reporter", "Created",
                     "Due date", "보류 code", "보류 사유", "댓글 히스토리",
                     "최종 결과(승인/반려 전환 결과 및 사유 & 날짜)", "IMG")
    else:
        header = _th("#", "Key", "Ticket Summary", "Reporter", "Created",
                     "Due date", "보류 code", "보류 사유", "댓글 히스토리",
                     "최종 결과(승인/반려 전환 결과 및 사유 & 날짜)", "IMG")

    rows = [header]
    for seq, t in enumerate(tickets, 1):
        hold_code = t.get("hold_code") or ""
        reason = t.get("background", "")[:100] if hold_code else ""
        if has_cycle_col:
            rows.append(_td(str(seq), cycle_label(t.get("cycle_number", 0)),
                            t.get("key", ""), t.get("summary", ""),
                            t.get("reporter", ""), t.get("created", ""), t.get("due_date", ""),
                            hold_code, reason, "", "", ""))
        else:
            rows.append(_td(str(seq), t.get("key", ""), t.get("summary", ""),
                            t.get("reporter", ""), t.get("created", ""), t.get("due_date", ""),
                            hold_code, reason, "", "", ""))

    return _table(widths, rows)


# ── 반려 티켓 테이블 (flat, KR 10열 / EU·HQ 10열) ───────────────
def _build_rejected_table(tickets, widths, has_cycle_col):
    if not tickets:
        return _no_tickets()

    if has_cycle_col:
        header = _th("#", "회차", "Key", "Ticket Summary", "Reporter", "Created",
                     "Due date", "반려 code", "반려 사유", "IMG")
    else:
        header = _th("#", "Key", "Ticket Summary", "Reporter", "Created",
                     "Due date", "반려 code", "반려 사유", "IMG")

    rows = [header]
    for seq, t in enumerate(tickets, 1):
        rej_code = t.get("rejection_code") or ""
        reason = t.get("problem", "")[:100] if rej_code else ""
        if has_cycle_col:
            rows.append(_td(str(seq), cycle_label(t.get("cycle_number", 0)),
                            t.get("key", ""), t.get("summary", ""),
                            t.get("reporter", ""), t.get("created", ""), t.get("due_date", ""),
                            rej_code, reason, ""))
        else:
            rows.append(_td(str(seq), t.get("key", ""), t.get("summary", ""),
                            t.get("reporter", ""), t.get("created", ""), t.get("due_date", ""),
                            rej_code, reason, ""))

    return _table(widths, rows)


# ── Section 0: 스크리닝 기준 ─────────────────────────────────────
def _build_section0():
    intro = _expand("스크리닝 프로세스 안내",
        _p("회차별 티켓/개선 티켓 스크리닝 운영 및 의견에서 이력 관리 및 관련 내용") +
        _p("▶ 본 문서") +
        _p("ㅇ 티켓 스크리닝 현황 및 이력 관리")
    )
    code_table = _table(CW.get("section1_overall", []), [
        _th_span([("보류", 1, 3), ("반려", 1, 4)]),
        _th("code", "유형", "판단 기준", "해소 조건", "code", "유형", "판단 기준"),
        _td("H1", "필수 항목 누락", "BRD 필수 항목 미작성 (추진 배경, 기능 목록, IT 연동 등)", "BRD 보완 후 재검토",
            "R1", "평가 항목 전항목 미충족", "시급성 해당 없음 + 5개 평가 항목 합계 0점"),
        _td("H2", "구체성 부족", "작성 항목의 요건 구체성 부족 또는 구현 로직 불명확", "요건 구체화 후 재검토",
            "R2", "운영 범위 외", "OneApp 플랫폼 운영 범위 외 요청 (타 시스템·채널 소관)"),
        _td("H3", "정량 근거 부족", "스코어링 근거가 추정 수준, 정량 데이터 보완 필요", "정량 데이터 보완 후 재검토",
            "R3", "중복 티켓", "실질적으로 동일한 요건이 이미 진행 중인 티켓 존재"),
        _td("H4", "선행 조건 미충족", "타 티켓/프로젝트 완료 또는 정책 확정이 선행 필요", "선행 조건 해소 후 재검토",
            "R4", "방향성 배치", "글로벌 BPM 방향성 또는 리더십 결정 사항과 배치"),
        _td("H5", "기타", "위 유형 외 기타 보류 사유", "사유 해소 후 재검토",
            "R5", "기타", "위 유형 외 기타 반려 사유"),
    ])
    return [
        intro,
        _h2("0. 티켓 스크리닝 기준"),
        code_table,
        _p("*code : 처리 품질 리스트에 적용되는 트래킹 코드 - H=Hold / R=Reject"),
    ]


# ── Section 1: 스크리닝 현황 ──────────────────────────────────────
def _build_section1(tickets, current_cycle):
    # 전체 현황 (6열)
    overall_rows = [
        _th_span([("", 2, 1), ("티켓 인입 수", 2, 1), ("승인", 2, 1), ("반려", 2, 1), ("보류", 2, 1)]),
    ]
    for group_label, regions in [("RHQ", ["KR", "EU"]), ("HQ", ["HQ"])]:
        for i, reg in enumerate(regions):
            full_label = REGION_LABEL[reg]
            cnt   = _cnt(tickets, reg)
            appr  = _cnt(tickets, reg, "Approved")
            rej   = _cnt(tickets, reg, "Rejected")
            pend  = _cnt(tickets, reg, ["Pending", "Pre-BRD"])
            if i == 0:
                rs = len(regions)
                overall_rows.append(
                    f"<tr><td rowspan='{rs}'><p>{group_label}</p></td>"
                    f"<td><p>{full_label}</p></td>"
                    f"<td><p>{cnt}</p></td><td><p>{appr}</p></td>"
                    f"<td><p>{rej}</p></td><td><p>{pend}</p></td></tr>"
                )
            else:
                overall_rows.append(
                    f"<tr><td><p>{full_label}</p></td>"
                    f"<td><p>{cnt}</p></td><td><p>{appr}</p></td>"
                    f"<td><p>{rej}</p></td><td><p>{pend}</p></td></tr>"
                )
    total_row = _td("Total", str(_cnt(tickets)), str(_cnt(tickets, approval="Approved")),
                    str(_cnt(tickets, approval="Rejected")),
                    str(_cnt(tickets, approval=["Pending", "Pre-BRD"])))
    overall_rows.append(total_row)
    overall_table = _table(CW["section1_overall"], overall_rows)

    # 회차별 트래킹 (19열)
    cycles = _get_all_cycles(tickets)
    track_rows = [
        _th_span([("", 2, 1), ("RHQ", 1, 10), ("HQ", 1, 4), ("Total", 1, 4)]),
        _th_span([("", 1, 1), ("KR", 1, 5), ("EU", 1, 5), ("GBCXD 및 타부문", 1, 4), ("", 1, 4)]),
        _th("회차",
            "인입", "승인", "반려", "보류중", "승인전환",
            "인입", "승인", "반려", "보류중", "승인전환",
            "인입", "승인", "반려", "보류",
            "인입", "승인", "반려", "보류"),
    ]
    for cn in cycles:
        c = [t for t in tickets if t.get("cycle_number") == cn]
        def _s(reg=None, appr=None):
            return str(_cnt(c, reg, appr))
        track_rows.append(_td(
            cycle_label(cn),
            _s("KR"), _s("KR","Approved"), _s("KR","Rejected"), _s("KR",["Pending","Pre-BRD"]), _s("KR","Approved"),
            _s("EU"), _s("EU","Approved"), _s("EU","Rejected"), _s("EU",["Pending","Pre-BRD"]), _s("EU","Approved"),
            _s("HQ"), _s("HQ","Approved"), _s("HQ","Rejected"), _s("HQ",["Pending","Pre-BRD"]),
            _s(), _s(appr="Approved"), _s(appr="Rejected"), _s(appr=["Pending","Pre-BRD"]),
        ))
    tracking_table = _table(CW["section1_tracking"], track_rows)

    # 회차별 마감 히스토리 expand
    hist_rows = [
        _th_span([("", 2, 1), ("RHQ", 1, 8), ("HQ", 1, 4)]),
        _th_span([("", 1, 1), ("KR", 1, 4), ("EU", 1, 4), ("GBCXD 및 타부문", 1, 4)]),
        _th("회차",
            "인입", "마감 시점 승인", "마감 시점 반려", "마감 시점 보류",
            "인입", "마감 시점 승인", "마감 시점 반려", "마감 시점 보류",
            "인입", "마감 시점 승인", "마감 시점 반려", "마감 시점 보류"),
    ]
    for cn in cycles:
        c = [t for t in tickets if t.get("cycle_number") == cn]
        def _s2(reg=None, appr=None):
            return str(_cnt(c, reg, appr))
        hist_rows.append(_td(
            cycle_label(cn),
            _s2("KR"), _s2("KR","Approved"), _s2("KR","Rejected"), _s2("KR",["Pending","Pre-BRD"]),
            _s2("EU"), _s2("EU","Approved"), _s2("EU","Rejected"), _s2("EU",["Pending","Pre-BRD"]),
            _s2("HQ"), _s2("HQ","Approved"), _s2("HQ","Rejected"), _s2("HQ",["Pending","Pre-BRD"]),
        ))
    history_expand = _expand("회차별 마감 히스토리", _table([], hist_rows))

    return [
        _h2("1. 티켓 스크리닝 현황"),
        _p(f"(업데이트) {datetime.now().strftime('%y.%m.%d')} 기준"),
        _h3("전체 현황"),
        overall_table,
        _h3("회차별 트래킹 현황"),
        tracking_table,
        history_expand,
    ]


# ── Section 2-4: 지역별 티켓 히스토리 ────────────────────────────
def _build_region_section(tickets, region_code, section_num, approved_widths,
                          pending_widths, rejected_widths, has_cycle_col):
    region_tickets = [t for t in tickets if t.get("region") == region_code]
    cycles = _get_all_cycles(region_tickets)
    region_name = {"KR": "KR", "EU": "EU", "HQ": "HQ GBCXD 및 타부문"}[region_code]

    def _filter(cyc=None, appr=None):
        result = region_tickets
        if cyc == 0:
            result = [t for t in result if t.get("cycle_number", 0) == 0]
        elif cyc is not None:
            result = [t for t in result if t.get("cycle_number") == cyc]
        if appr:
            if isinstance(appr, list):
                result = [t for t in result if t.get("brd_approval") in appr]
            else:
                result = [t for t in result if t.get("brd_approval") == appr]
        return result

    parts = [_h2(f"{section_num}. {region_name} 티켓 히스토리")]

    # 승인 티켓
    parts.append(_p(f"{section_num}.1. 승인 티켓"))
    prebrd_approved = _filter(0, "Approved")
    parts.append(_expand("Pre-BRD",
        _build_approved_table(prebrd_approved, approved_widths, has_cycle_col, is_prebrd=True)))
    for cn in cycles:
        cycle_approved = _filter(cn, "Approved")
        title = _cycle_expand_title(cn)
        parts.append(_expand(title,
            _build_approved_table(cycle_approved, approved_widths, has_cycle_col)))

    # 보류 티켓
    parts.append(_p(f"{section_num}.2. 보류 티켓"))
    prebrd_pending = _filter(0, ["Pending", "Pre-BRD"])
    parts.append(_expand("Pre-BRD",
        _build_pending_table(prebrd_pending, pending_widths, has_cycle_col)))
    for cn in cycles:
        cycle_pending = _filter(cn, ["Pending", "Pre-BRD"])
        title = _cycle_expand_title(cn)
        parts.append(_expand(title,
            _build_pending_table(cycle_pending, pending_widths, has_cycle_col)))

    # 반려 티켓
    parts.append(_p(f"{section_num}.3. 반려 티켓"))
    prebrd_rejected = _filter(0, "Rejected")
    parts.append(_expand("Pre-BRD",
        _build_rejected_table(prebrd_rejected, rejected_widths, has_cycle_col)))
    for cn in cycles:
        cycle_rejected = _filter(cn, "Rejected")
        title = _cycle_expand_title(cn)
        parts.append(_expand(title,
            _build_rejected_table(cycle_rejected, rejected_widths, has_cycle_col)))

    return parts


# ── 메인 업데이트 함수 ──────────────────────────────────────────
def update(tickets_with_analysis: list[dict], client: ConfluenceClient | None = None):
    if client is None:
        client = ConfluenceClient()

    current_cycle = max((t.get("cycle_number", 0) for t in tickets_with_analysis), default=0)

    sections = []
    sections += _build_section0()
    sections += _build_section1(tickets_with_analysis, current_cycle)
    sections += _build_region_section(
        tickets_with_analysis, "KR", 2,
        CW["kr_approved"], CW["kr_pending"], CW["kr_rejected"], has_cycle_col=True)
    sections += _build_region_section(
        tickets_with_analysis, "EU", 3,
        CW["eu_approved"], CW["eu_pending"], CW["eu_rejected"], has_cycle_col=False)
    sections += _build_region_section(
        tickets_with_analysis, "HQ", 4,
        CW["eu_approved"], CW["eu_pending"], CW["eu_rejected"], has_cycle_col=False)

    html = "\n".join(sections)

    timestamp = datetime.now().strftime("%m-%d %H:%M")
    title = f"{timestamp} 신규/개선 전체 현황 (AI 생성)"
    parent_id = DOC_PAGE_IDS["doc2"]

    result = client.create_page(parent_id, title, html)
    new_id = result.get("id", "")
    print(f"[Doc2] 완료  총 {len(tickets_with_analysis)}건")
    print(f"[Doc2] 새 페이지: {title}  (id={new_id})")
