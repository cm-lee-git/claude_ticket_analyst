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
"""


def analyze_ticket(ticket: dict) -> dict:
    """티켓 1건을 분석하여 summary_ko, background, problem, feature, scores, priority_score 반환."""
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
        start = raw.find("{")
        end = raw.rfind("}") + 1
        parsed = json.loads(raw[start:end])

    scores = parsed.get("scores", {})
    # Priority = 5개 항목 합산 (urgency 제외), 각 0 또는 1
    parsed["priority_score"] = int(sum(scores.get(k, 0) for k in SCORE_KEYS_FOR_PRIORITY))

    if "summary" in parsed and "summary_ko" not in parsed:
        parsed["summary_ko"] = parsed.pop("summary")
    return parsed


def analyze_tickets_batch(tickets: list[dict]) -> list[dict]:
    """여러 티켓을 순차 분석. description을 개별 조회 후 분석 결과 병합하여 반환."""
    jira = JiraClient()
    results = []
    for t in tickets:
        if not t.get("description"):
            t["description"] = jira.get_description(t["key"])
        try:
            analysis = analyze_ticket(t)
        except Exception:
            analysis = {
                "summary_ko": "",
                "background": "",
                "problem": "",
                "feature_label": "기존 기능 개선",
                "feature": "",
                "scores": {k: 0 for k in ["urgency"] + SCORE_KEYS_FOR_PRIORITY},
                "priority_score": 0,
            }
        results.append({**t, **analysis})
    return results
