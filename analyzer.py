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
- summary_ko: 1~2문장 요약 (현재 상태, 핵심 내용 포함)
- background / problem / feature: 각 핵심 포인트를 개행(\\n)으로 구분하여 2~4개 작성
  예) "주요 배경 포인트 A\\n주요 배경 포인트 B\\n주요 배경 포인트 C"

{
  "summary_ko": "티켓 상태 및 간략 정보 (한국어, 1~2문장)",
  "background": "핵심 배경 포인트1\\n핵심 배경 포인트2 (한국어, \\n 구분)",
  "problem": "핵심 문제 포인트1\\n핵심 문제 포인트2 (한국어, \\n 구분)",
  "feature_label": "기존 기능 개선 또는 신규 기능 중 하나",
  "feature": "기능 상세 포인트1\\n기능 상세 포인트2 (한국어, \\n 구분)",
  "hold_code": "보류 시 H1~H5 중 하나, 아니면 null",
  "rejection_code": "반려 시 R1~R5 중 하나, 아니면 null",
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

### hold_code (BRD 상태가 Pending/보류일 때만 작성, 아니면 null)
- H1: BRD 필수 항목 미작성 (추진 배경, 기능 목록, IT 연동 등)
- H2: 작성 항목의 요건 구체성 부족 또는 구현 로직 불명확
- H3: 스코어링 근거가 추정 수준, 정량 데이터 보완 필요
- H4: 타 티켓/프로젝트 완료 또는 정책 확정이 선행 필요
- H5: 위 유형 외 기타 보류 사유

### rejection_code (BRD 상태가 Rejected/반려일 때만 작성, 아니면 null)
- R1: 시급성 해당 없음 + 5개 평가 항목 합계 0점 (자동 판별)
- R2: OneApp 플랫폼 운영 범위 외 요청 (타 시스템·채널 소관)
- R3: 실질적으로 동일한 요건이 이미 진행 중인 티켓 존재
- R4: 글로벌 BPM 방향성 또는 리더십 결정 사항과 배치
- R5: 위 유형 외 기타 반려 사유
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
    desc_len = len(ticket.get('description', ''))
    print(f"  [claude-in]  {ticket['key']}: description={desc_len}자, summary={ticket['summary'][:40]!r}")

    client = _get_client()
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
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
            ticket.get("brd_approval") == "Rejected"):
        parsed["rejection_code"] = "R1"

    if "summary" in parsed and "summary_ko" not in parsed:
        parsed["summary_ko"] = parsed.pop("summary")
    return parsed


def analyze_tickets_batch(tickets: list[dict]) -> list[dict]:
    """여러 티켓을 순차 분석. description을 개별 조회 후 분석 결과 병합하여 반환."""
    jira = JiraClient()
    results = []
    for t in tickets:
        key = t.get("key", "?")
        if not t.get("description"):
            # search에서 못 가져온 경우 개별 조회로 보완
            t["description"] = jira.get_description(key)
        else:
            print(f"  [description] {key}: {len(t['description'])}자 (search에서 수신)")
        try:
            analysis = analyze_ticket(t)
            scores = analysis.get("scores", {})
            o_count = sum(1 for v in scores.values() if float(v or 0) > 0)
            print(f"  [분석] {key}: scores O={o_count}/6  priority={analysis.get('priority_score', 0)}")
        except Exception as e:
            print(f"  [분석] {key}: 분석 실패 → {e}")
            analysis = {
                "summary_ko": "",
                "background": "",
                "problem": "",
                "feature_label": "기존 기능 개선",
                "feature": "",
                "hold_code": None,
                "rejection_code": None,
                "scores": {k: 0 for k in ["urgency"] + SCORE_KEYS_FOR_PRIORITY},
                "priority_score": 0,
            }
        results.append({**t, **analysis})
    return results
