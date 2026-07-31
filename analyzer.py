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
  "summary": "티켓 상태 및 간략 정보 (한국어, 2~3문장)",
  "background": "배경 (한국어)",
  "problem": "문제 (한국어)",
  "feature": "기능 개선 또는 신규 기능 (한국어)",
  "scores": {
    "urgency": 0,
    "business_performance": 0,
    "customer_experience": 0,
    "operational_efficiency": 0,
    "global_reach": 0,
    "platform_strategy": 0
  }
}

점수 기준 (각 0~5):
- urgency: 주요 장애 / 법적 컴플라이언스 / 리더십 주도 이니셔티브
- business_performance: 판매/구매 전환 영향
- customer_experience: 고객 만족 개선 / 불편 해소
- operational_efficiency: 반복 작업 제거 / 비용 절감
- global_reach: MAU 200만+ 커버리지 + 수혜국 비율 50%+
- platform_strategy: KR(원격제어/정비/충전), EU(앱 다운로드/등록), Global(Non-CCS/CCS 표준화) KPI 연계
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
                "summary": f"분석 실패: {e}",
                "background": "",
                "problem": "",
                "feature": "",
                "scores": {k: 0 for k in SCORE_WEIGHTS},
                "priority_score": 0.0,
            }
        results.append({**t, **analysis})
    return results
