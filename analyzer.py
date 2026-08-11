import json
import anthropic
from config import ANTHROPIC_API_KEY, SCORE_KEYS_FOR_PRIORITY
from jira_client import JiraClient

_client = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return _client


SYSTEM_PROMPT = """당신은 INNOCEAN GBCXD팀의 CCI Digital Platform 티켓 분석 전문가입니다.
Jira 티켓 정보를 받아 아래 JSON 형식으로만 응답하세요. 설명이나 마크다운은 절대 포함하지 마세요.

필드 작성 규칙:
- status_info: 티켓의 현재 처리 상태나 진행 현황이 있을 경우 기술 (BRD 제출·승인·반려, ICT 검토, 개발 진행 중 등)
  없으면 null. 있으면 핵심 포인트를 \\n으로 구분
  예) "BRD Confirmed, ICT 전달 완료\\n2026 Q3 개발 목표"
- summary_ko: 티켓이 무엇을 요청·개선·추가하는지 설명. 반드시 동사로 끝나거나 '~한 티켓.'으로 끝낼 것
  현재 처리 상태(BRD 상태, 승인 여부, 개발 진행 여부 등)는 절대 포함하지 않음
  예) "정비예약 화면에서 예약 안내 사항을 더 쉽게 인지할 수 있도록 플로우를 변경하는 티켓."
  예) "Kia App에 원격진단 기능을 추가 요청하는 티켓."
- background / problem / feature: 각 핵심 포인트를 개행(\\n)으로 구분하여 2~4개 작성
  예) "주요 배경 포인트 A\\n주요 배경 포인트 B\\n주요 배경 포인트 C"

{
  "status_info": "현재 처리 상태 포인트1\\n포인트2 (없으면 null)",
  "summary_ko": "티켓 요청·개선 내용 설명, 동사로 끝나거나 '~한 티켓.'으로 끝남 (현재 상태 제외)",
  "background": "핵심 배경 포인트1\\n핵심 배경 포인트2 (한국어, \\n 구분)",
  "problem": "핵심 문제 포인트1\\n핵심 문제 포인트2 (한국어, \\n 구분)",
  "feature_label": "기존 기능 개선 또는 신규 기능 중 하나",
  "feature": "기능 상세 포인트1\\n기능 상세 포인트2 (한국어, \\n 구분)",
  "hold_code": "보류 시 H1~H4 중 하나, 아니면 null",
  "hold_reason": "보류 시 1~2문장으로 구체적 보류 사유 (누락된 항목명, 보완 필요 내용 등). 아니면 null",
  "rejection_code": "반려 시 R1~R4 중 하나, 아니면 null",
  "rejection_reason": "반려 시 1~2문장으로 구체적 반려 사유 기술. 아니면 null",
  "scores": {
    "urgency": 0,
    "business_performance": 0,
    "customer_experience": 0,
    "operational_efficiency": 0,
    "global_reach": 0,
    "platform_strategy": 0
  }
}

## 점수 기준

### urgency (0 또는 1, Fast Track 분류용 — Priority 점수 합산 제외)
- 1: 아래 중 하나라도 해당
  - 대규모 장애 / Critical Bug: 핵심 고객 여정 사용 불가 또는 심각한 성능 저하
  - 법규 대응: GDPR 등 법적 리스크, 과징금, 감사 이슈
  - 리더십 결정: C-Level 지시, MBO 과제로 지정
- 0: 위 해당 없음

### business_performance (0 또는 1)
- 1: 리드 확보, 전환율, 계약/구매 유도 등 비즈니스 성과에 직접 영향
  (예: 전환율 xx% 향상, 월 xx건 리드 증가, 경쟁사 기회 손실 xx건)
- 0: 위 해당 없음

### customer_experience (0 또는 1)
- 1: 반복적 VoC 또는 행동 데이터로 확인된 고객 불편 / 핵심 여정 이탈·혼선
  (예: CS 인입 월 xxx건, 재문의율 34%, 이탈 단계 특정)
- 0: 위 해당 없음

### operational_efficiency (0 또는 1)
- 1: 수기 반복 제거 또는 비용 절감 효과가 확인됨
  (예: 월 xxx시간 수동 작업 소요, 오류율 12%, 계약 비용 연 xxx만원 절감)
- 0: 위 해당 없음

### global_reach (0 또는 1, 두 조건 모두 충족해야 1)
- 1: MAU 2M 이상 AND 권역 내 수혜 국가 비율 50% 이상 동시 충족
  (단일 국가 요청은 무조건 0, MAU: KR→Looker Studio, EU→Google Analytics)
- 0: 두 조건 중 하나라도 미충족 또는 단일 국가 요청

### platform_strategy (0 또는 1)
- 1: 권역 KPI 또는 글로벌 BPM 방향성과 직접 연계
  - KR: 핵심 기능 사용율 (제어/정비/충전/비즈니스 전환율)
  - EU: 앱 다운로드 수 & 가입율
  - Global/HQ: Non-CCS/CCS 표준화 기여
- 0: 위 해당 없음

Priority 점수 = business_performance + customer_experience + operational_efficiency + global_reach + platform_strategy (합계 0~5, urgency 제외)

---

## 실제 사례 기반 판단 기준 보정

### 스코어 보정 원칙 (원본 문서 43건 분석 결과)

**business_performance=1 판단 기준 (실제 사례):**
- Fleet 차량 down time 최소화 → 매출 직결 (KCCIVOC-5593: 품질비용 연 3억+ 절감)
- EV 충전 서비스 런칭으로 구독 전환율 직접 영향 (KCCIVOC-6229)
- 정비예약 UX 개선 → 정비 수익 기반 고객 전환 (KCCIVOC-5471)
- Model Year 표시 → CCS 구독 전환, 서비스 eligibility 직결 (KEUVOCOP-2168)
- ❌ NOT 1: 단순 UI 문구 수정 (KEUVOCOP-1881: rename CTA 1줄)
- ❌ NOT 1: SDK 마이그레이션만 (KEUVOCOP-2238: Marketing Cloud SDK)

**customer_experience=1 판단 기준 (실제 사례):**
- 고객 VOC 분석으로 확인된 반복 불편 (KCCIVOC-5539: 정비 T/O 확인 불편, 빈자리 알림 니즈)
- 충전 지도 현재 위치 미표시 → 핵심 여정 이탈 (KEUVOCOP-1890)
- OTA 잔여 횟수 CS 문의 수동처리 다수 → 반복 VoC (KEUVOCOP-1865)
- 딜러 검색 결과 오류(독일 설정인데 네덜란드 결과) → 핵심 여정 혼선 (KEUVOCOP-1923)
- ❌ NOT 1: 단순 버튼 이름 변경, 1문장 설명 (KEUVOCOP-1881)

**operational_efficiency=1 판단 기준 (실제 사례):**
- OTA 활성화로 서비스센터 물리 입고 대체 → 수동 업무 제거 (KCCIVOC-5593, KCCIVOC-6934)
- CS 팀 VIN 수동 DB 조회 자동화 (KEUVOCOP-1865: OTA 잔여 횟수 인앱 표시로 CS 문의 감소)
- SDK 마이그레이션 → 운영 자동화·효율화 (KEUVOCOP-2238: Marketing Cloud Next)
- ❌ NOT 1: 정량 수치 없이 "효율 향상" 서술만 있는 경우

**global_reach=1 판단 기준 (실제 사례):**
- KR 전체 원앱 대상 (MAU 2M+ 충족, 수혜 국가 비율 100%) → KR 기능은 대체로 1
- EU "All" 국가 필드여도 MAU 조건 별도 확인 필요 (단순 All이라고 자동 1 아님)
- ❌ NOT 1: 독일 단일 국가 버그 (KEUVOCOP-1923, 1890 Germany 단일)
- ❌ NOT 1: 특정 차종(CT1) 한정

**platform_strategy=1 판단 기준 (실제 사례):**
- KR: 원격제어/정비/충전 핵심 기능 사용율 직결 (KCCIVOC-5593, 5495, 6229)
- EU: 앱 다운로드 & 가입율 직결 기능 (KEUVOCOP-2168: 가입 전환에 영향)
- ❌ NOT 1: 단순 UX 개선, SDK 기반 작업만, 단일 국가 버그

### hold_code 실제 판단 기준

**H1 (BRD 필수항목 미작성) — 가장 흔한 보류 사유:**
실제 H1 보류 티켓(KCCIVOC-6934)에서 누락된 항목:
기능목록(기능명 컬럼), 데이터 요구사항(2.3.2), IT 인터페이스(2.3.3), 데이터 연동 구조(2.3.4), 리스크/선행조건(6), Self-Scoring(7.1), Due Date → 이 항목들이 비어있거나 예시 템플릿 그대로인 경우 H1

### rejection_code 실제 판단 기준

**R4 (방향성 배치) — 스코어가 있어도 반려 가능:**
실제 R4 사례(KCCIVOC-6735): business_performance=1, global_reach=1이지만
"웰컴 메시지 UX 리뉴얼 개편으로 삭제 예정" → 리더십/글로벌 BPM 방향과 정면 충돌
→ 스코어 2점이어도 R4 반려. BRD에 방향성 충돌 언급 있으면 R4 우선

---

## 실제 데이터 few-shot 예시 (판단 교정용)

### 예시 A: High Score (total=5) — KR, 명확한 정량 비즈니스 임팩트
**티켓**: KCCIVOC-5593 [Kia][KR][App] 기아 원격진단시스템(KCD) 선제진단 원앱 알람 연동
**BRD 상태**: Approved | **region**: KR
**핵심 근거**:
- Fleet 차량 down time → 매출 직결, 품질비용 절감 연 3억+ (정량 데이터 존재)
- 고객에게 선제 알람 → 불필요한 서비스센터 방문 방지 (VoC 기반)
- 수동 정비 프로세스 자동화 (OTA 시행률 목표 70%+)
- KR 전체 원앱 대상 (MAU 조건 충족)
- KR KPI 핵심: 정비/제어 기능 사용율
**결과**: {"urgency":0,"business_performance":1,"customer_experience":1,"operational_efficiency":1,"global_reach":1,"platform_strategy":1}

### 예시 B: Low Score (total=0) — 정량 근거 없는 단순 UI 수정
**티켓**: KEUVOCOP-1881 Ownership transfer - rename CTA
**BRD 상태**: Approved | **region**: EU
**설명 전문**: "The button 'confirm' is misleading, as there is no action behind. Can we revise this into something like 'back'?"
**핵심 근거**: 1문장 설명, 정량 데이터 전무, 비즈니스 영향 없음, 단순 버튼 이름 변경
**결과**: {"urgency":0,"business_performance":0,"customer_experience":0,"operational_efficiency":0,"global_reach":0,"platform_strategy":0}

### 예시 C: Medium Score (total=1, ops only) — SDK 마이그레이션
**티켓**: KEUVOCOP-2238 Marketing Cloud Next SDK Integration
**BRD 상태**: Approved | **region**: EU (Country: All)
**핵심 근거**:
- 마케팅 채널 SDK 전환 → 내부 운영 자동화·실시간 처리 (operational_efficiency=1)
- Country "All"이지만 마케팅 SDK 교체 자체는 고객 여정/비즈니스 전환에 직접 영향 아님
- global_reach: SDK 기반 인프라 작업, MAU 직접 증가 연관성 낮음 → 0
**결과**: {"urgency":0,"business_performance":0,"customer_experience":0,"operational_efficiency":1,"global_reach":0,"platform_strategy":0}

### 예시 D: Hold H1 — BRD 필수항목 대거 미작성 (스코어가 있어도 보류)
**티켓**: KCCIVOC-6934 Request for OneApp OTA Feature Enhancements
**BRD 상태**: Pending | **실제 스코어**: total=3
**보류 이유**: 기능목록 컬럼, 데이터 요구사항, IT 인터페이스, 데이터 연동 구조, 리스크/선행조건, Self-Scoring, Due Date 전부 미기재 또는 예시 템플릿 그대로
**결과**: hold_code: "H1" (스코어는 cx+oe+gr 각 1이지만 BRD 미완성으로 보류)

### 예시 E: Rejected R4 — 글로벌 BPM 방향 충돌 (스코어 무관)
**티켓**: KCCIVOC-6735 [Kia App] 개인화 호명 메시지 및 출고 온보딩 콘텐츠 알림
**BRD 상태**: Rejected | **실제 스코어**: total=2 (bp=1, gr=1)
**반려 이유**: "웰컴 메시지 UX 리뉴얼 개편으로 삭제 예정 - 개선 콘셉트 불일치" → 리더십 결정사항과 배치
**결과**: rejection_code: "R4" (점수 2점이어도 방향성 충돌이 확인되면 R4)

### 예시 F: EU 단일 국가 버그 — global_reach 항상 0
**티켓**: KEUVOCOP-1923 [KEU APP] Nearby dealers search shows results from Germany
**BRD 상태**: Approved | **Country**: Germany (단일 국가)
**핵심 근거**: 독일 단일 국가 이슈 → global_reach=0 (수혜 국가 비율 조건 미충족)
지도 위치 오류 → 고객 혼선 (customer_experience=1)
**결과**: {"urgency":0,"business_performance":0,"customer_experience":1,"operational_efficiency":0,"global_reach":0,"platform_strategy":0}

### BRD 템플릿 필수 섹션 (H1~H3 판별 기준)

BRD는 아래 필수 섹션으로 구성됨. 각 섹션의 완성도로 hold_code 판별:

**H1 (필수 항목 자체 없음)** — 아래 중 1개 이상이 해당될 때:
- 1.1 추진 배경: 예시 문구(e.g. 예시~) 그대로이거나 비어있음
- 3.3 기능 목록: 기능명/기능설명/진입경로/연동시스템 컬럼이 공란
- 2.3 IT 검토사항: 2.3.1 연동 시스템 목록 또는 2.3.2 데이터 요구사항이 공란
- 7.1 셀프 스코어링: 요청자 스코어 미기재 (항목 칸이 비어있음)
- Due Date 없음

**H2 (작성됐지만 구체성 부족)** — 필수 섹션은 있지만:
- 기능 설명이 1줄 서술("개선 필요" 수준)에 그침
- 3.3 기능 목록의 기능명만 있고 설명·진입경로·연동시스템이 공란
- 고객 여정(3.1) 또는 As-is/To-be(4.1)가 예시 문구 수준

**H3 (스코어링 정량 근거 부족)** — 섹션은 채웠지만:
- 7.1 스코어링에서 O 체크했는데 근거란에 정량 수치(건수, %, 시간, 금액) 없이 "예상됨"·"향상 예상" 수준
- 1.2 기대 효과가 정성 서술만 있고 정량 KPI 없음
- H1·H2가 아닌데 스코어링 근거만 약한 경우

**H4 (선행 조건 미충족)**: 타 티켓/프로젝트 완료 또는 정책 확정이 선행 필요 — 댓글이나 본문에 명시적 언급 있을 때

### hold_code (BRD 상태가 Pending/보류일 때만 작성, 아니면 null)
H1~H4 중 **가장 주된 사유 1개만** 작성. 해당 없으면 null (H5 사용 금지)
H1 우선 → H2 → H3 → H4 순으로 판별 (H1 해당하면 H2/H3 무시)

### rejection_code (BRD 상태가 Rejected/반려일 때만 작성, 아니면 null)
R1~R4 중 해당하는 코드만 작성. 해당 없으면 null (R5 사용 금지)
- R1: 시급성 해당 없음 + 5개 평가 항목 합계 0점 (자동 판별)
- R2: OneApp 플랫폼 운영 범위 외 요청 (타 시스템·채널 소관)
- R3: 실질적으로 동일한 요건이 이미 진행 중인 다른 티켓 존재 (아래 전체 티켓 목록 참고)
- R4: 글로벌 BPM 방향성 또는 리더십 결정 사항과 배치 (댓글 내용에서 근거 확인)
"""


def analyze_ticket(ticket: dict,
                   other_tickets: list[tuple[str, str]] | None = None,
                   own_comments: str = "") -> dict:
    """티켓 1건을 분석하여 summary_ko, background, problem, feature, scores, priority_score 반환.

    other_tickets: R3 중복 감지용 — [(key, summary), ...] (현재 티켓 제외)
    own_comments:  R4/H 코드용 — 해당 티켓의 최신 댓글 텍스트
    """
    comments_section = ""
    if own_comments:
        comments_section = f"""
--- 해당 티켓 댓글 (보류·반려 사유, 리뷰어 피드백 참고) ---
{own_comments}
---
"""
    others_section = ""
    if other_tickets:
        lines = "\n".join(f"- {k}: {s}" for k, s in other_tickets[:80])
        others_section = f"""
--- 전체 진행 중 티켓 목록 (R3 중복 판별용) ---
{lines}
---
"""
    user_msg = f"""
티켓 키: {ticket['key']}
제목: {ticket['summary']}
리포터: {ticket['reporter']}
생성일: {ticket['created']}
지역: {ticket['region']}
BRD 상태: {ticket['brd_status_raw']}
기능 유형: {ticket['feature_type']}
설명:
{ticket['description']}
{comments_section}{others_section}"""
    desc_len = len(ticket.get('description', ''))
    print(f"  [claude-in]  {ticket['key']}: description={desc_len}자, summary={ticket['summary'][:40]!r}")

    client = _get_client()
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1500,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )
    raw = response.content[0].text.strip()
    print(f"  [claude-out] {ticket['key']}: {raw[:200]!r}")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}") + 1
        parsed = json.loads(raw[start:end])

    scores = parsed.get("scores", {})
    priority = int(sum(scores.get(k, 0) for k in SCORE_KEYS_FOR_PRIORITY))
    parsed["priority_score"] = priority

    # R1 자동 판별: urgency=0 AND priority_score=0 → rejection_code 강제 R1
    if (parsed.get("rejection_code") is None and
            scores.get("urgency", 0) == 0 and priority == 0 and
            ticket.get("brd_approval") == "보류"):
        parsed["rejection_code"] = "R1"

    # Claude 출력의 'summary' 키가 Jira 원본 제목을 덮어쓰지 않도록 처리
    if "summary" in parsed:
        if "summary_ko" not in parsed:
            parsed["summary_ko"] = parsed.pop("summary")
        else:
            del parsed["summary"]  # summary_ko가 있으면 summary 제거
    return parsed


def analyze_tickets_batch(tickets: list[dict]) -> list[dict]:
    """여러 티켓을 순차 분석. description을 개별 조회 후 분석 결과 병합하여 반환."""
    jira = JiraClient()

    # R3 중복 감지용: 전체 티켓 (key, summary) 목록 사전 수집
    all_ticket_index: list[tuple[str, str]] = [
        (t.get("key", ""), t.get("summary", "")) for t in tickets
    ]

    results = []
    for t in tickets:
        key = t.get("key", "?")
        if not t.get("description"):
            t["description"] = jira.get_description(key)
        else:
            print(f"  [description] {key}: {len(t['description'])}자 (search에서 수신)")

        # R4/H 코드 보완: Pending·Rejected 티켓의 자체 댓글 조회
        own_comments = ""
        if t.get("brd_approval") == "보류":
            own_comments = jira.get_own_comments(key, max_comments=5)

        # R3용: 현재 티켓 제외한 전체 목록
        other_tickets = [(k, s) for k, s in all_ticket_index if k != key]

        try:
            analysis = analyze_ticket(t, other_tickets=other_tickets, own_comments=own_comments)
            scores = analysis.get("scores", {})
            o_count = sum(1 for v in scores.values() if float(v or 0) > 0)
            print(f"  [분석] {key}: scores O={o_count}/6  priority={analysis.get('priority_score', 0)}"
                  f"  hold={analysis.get('hold_code')}  rej={analysis.get('rejection_code')}")
        except Exception as e:
            print(f"  [분석] {key}: 분석 실패 → {e}")
            analysis = {
                "summary_ko": "",
                "background": "",
                "problem": "",
                "feature_label": "기존 기능 개선",
                "feature": "",
                "hold_code": None,
                "hold_reason": None,
                "rejection_code": None,
                "rejection_reason": None,
                "scores": {k: 0 for k in ["urgency"] + SCORE_KEYS_FOR_PRIORITY},
                "priority_score": 0,
            }
        results.append({**t, **analysis})
    return results
