import json
import anthropic
from config import ANTHROPIC_API_KEY, SCORE_WEIGHTS
from jira_client import JiraClient

_client = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return _client


SYSTEM_PROMPT = """당신은 INNOCEAN GBCXD팀의 CCI Digital Platform 티켓 분석 전문가입니다.
Jira 티켓 정보를 받아 아래 JSON 형식으로만 응답하세요. 설명이나 마크다운은 절대 포함하지 마세요.

{
  "summary_ko": "티켓 상태 및 간략 정보 (한국어, 2~3문장)",
  "background": "배경 (한국어)",
  "problem": "문제 (한국어)",
  "feature_label": "기존 기능 개선 또는 신규 기능 중 하나",
  "feature": "해당 기능의 상세 내용 (한국어)",
  "scores": {
    "urgency": 0,
    "business_performance": 0,
    "customer_experience": 0,
    "operational_efficiency": 0,
    "global_reach": 0,
    "platform_strategy": 0
  }
}

점수 기준:

[urgency] 0 또는 1만 사용 (Fast Track 분류용 이진값)
- 1(O): 아래 중 하나라도 해당
  - 대규모 장애 / Critical Bug: 핵심 고객 여정 사용 불가 또는 심각한 성능 저하
  - 법규 대응: GDPR 등 법적 리스크, 과징금, 감사 이슈
  - 리더십 결정: C-Level 지시, MBO 과제로 지정
- 0(X): 위 기준 해당 없음

[business_performance] 0~5점
- 0: 사업 성과와 무관
- 1~2: 간접 기여 (사용성 개선 등, 수치 근거 없음)
- 3~4: 직접적 전환율/리드 영향 명시 (수치 근거 있음)
- 5: 핵심 전환 Funnel 직접 영향 + 경쟁사 기회 손실 + 명확한 수치 근거
  (예: 전환율 xx% 향상, 월 xx건 리드 증가, 경쟁사 동일 기능 비교 손실)

[customer_experience] 0~5점
- 0: 고객 경험과 무관
- 1~2: 소수 고객 불편, 우회 가능, VoC 미미
- 3~4: 반복적 VoC 또는 행동 데이터로 확인된 불편 (CS 인입 건수, 이탈률 등 근거)
- 5: 핵심 여정 구조적 이탈/실패 + 명확한 CS/데이터 근거 + 재사용율/신뢰도 영향
  (예: CS 인입 월 xxx건, 재문의율 34%, 이탈 단계 특정)
[operational_efficiency] 0~5점
- 0: 운영 효율화와 무관
- 1~2: 소규모 반복 작업, 수치 근거 없음
- 3~4: 수동 작업량 또는 비용 데이터 명시 (시간·비용 수치 있음)
- 5: 대규모 인력/시간 절감 + 품질 리스크 해소 + 비용 절감 수치 모두 구체적
  (예: 월 xxx시간 소요, 오류율 12%, 계약 비용 연 xxx만원 절감)
[global_reach] 0~5점 (두 조건 동시 충족 필요)
- 0: 단일 국가 적용 또는 MAU 2M 미만 (단일 국가 권역은 0점)
- 1~2: MAU 2M 이상 또는 수혜 국가 50% 이상 중 하나만 충족
- 3~4: MAU 2M 이상 + 수혜 국가 50% 이상 (수치 일부 약함)
- 5: MAU 2M 이상 + 수혜 국가 50% 이상 + 타 기능/서비스 확장 효과 확인
  (MAU 확인: KR→Looker Studio, EU→Google Analytics)
[platform_strategy] 0~5점
- 0: KPI 또는 전략 방향과 무관
- 1~2: 해당 권역 KPI와 간접 연계
- 3~4: 권역 KPI 직접 연계 (KPI 갭 수치 또는 BPM 방향성 언급)
- 5: 권역 KPI 직접 연계 + 글로벌 BPM 과제 연계 + 타 권역 확산 가능성 확인
  권역별 KPI 기준:
  - KR: 핵심 기능 사용율 (제어/정비/충전/비즈니스 전환율)
  - EU: 앱 다운로드 수 & 가입율
  - Global/HQ: Non-CCS/CCS 표준화 기여
"""


def analyze_ticket(ticket: dict) -> dict:
    """티켓 1건을 분석하여 summary, background, problem, feature, scores, priority_score 반환."""
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
"""
    client = _get_client()
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )
    raw = response.content[0].text.strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        # JSON 추출 재시도
        start = raw.find("{")
        end = raw.rfind("}") + 1
        parsed = json.loads(raw[start:end])

    scores = parsed.get("scores", {})
    priority = sum(scores.get(k, 0) * w for k, w in SCORE_WEIGHTS.items())
    parsed["priority_score"] = round(priority, 2)
    # summary_ko 로 통일 (summary 키가 오면 summary_ko 로 이동)
    if "summary" in parsed and "summary_ko" not in parsed:
        parsed["summary_ko"] = parsed.pop("summary")
    return parsed


def analyze_tickets_batch(tickets: list[dict]) -> list[dict]:
    """여러 티켓을 순차 분석. description을 개별 조회 후 분석 결과 병합하여 반환."""
    jira = JiraClient()
    results = []
    for t in tickets:
        # description 개별 조회
        if not t.get("description"):
            t["description"] = jira.get_description(t["key"])
        try:
            analysis = analyze_ticket(t)
        except Exception as e:
            analysis = {
                "summary_ko": "",
                "background": "",
                "problem": "",
                "feature_label": "기존 기능 개선",
                "feature": "",
                "scores": {k: 0 for k in SCORE_WEIGHTS},
                "priority_score": 0.0,
            }
        results.append({**t, **analysis})
    return results
