import os
from dotenv import load_dotenv

load_dotenv()

# Jira: HMG (현대자동차그룹) 인스턴스
JIRA_BASE_URL = "https://hmg.atlassian.net"
JIRA_EMAIL = os.getenv("JIRA_EMAIL")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN")

# Confluence: IHQDF (이노션) 인스턴스
CONFLUENCE_BASE_URL = "https://ihqdf.atlassian.net"
CONFLUENCE_EMAIL = os.getenv("CONFLUENCE_EMAIL")
CONFLUENCE_API_TOKEN = os.getenv("CONFLUENCE_API_TOKEN")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

JIRA_PROJECTS = ["CCIPRJ", "KCCIVOC", "KEUVOCOP"]

CONFLUENCE_PARENT_PAGE_ID = "68222989"

# 구조 참조용 복사본 페이지 ID (읽기 전용)
DOC_TEMPLATE_IDS = {
    "doc1": "70156303",   # 복사본: KKR OneApp 주간 보고
    "doc2": "70025250",   # 복사본: 신규/개선 티켓 스크리닝
    "doc3": "70058046",   # 복사본: (Kia) 신규/개선
}

# 자동화 업데이트 대상 페이지 ID (AI 생성 폴더)
DOC_PAGE_IDS = {
    "doc1": "71368772",   # AI 생성: KKR OneApp 주간 보고
    "doc2": "71368792",   # AI 생성: 신규/개선 티켓 스크리닝
    "doc3": "71303264",   # AI 생성: (Kia) 신규/개선
}

# 각 문서 페이지 제목 (부분 일치로 탐색, 폴백용)
DOC_TITLE_KEYWORDS = {
    "doc1": "KKR",
    "doc2": "신규/개선",       # (Kia) 제외
    "doc3": "(Kia) 신규/개선",
}

# Jira 커스텀 필드 ID (.env에서 오버라이드 가능)
JIRA_FIELDS = {
    "country":      os.getenv("JIRA_FIELD_COUNTRY",      "customfield_10100"),
    "brd_status":   os.getenv("JIRA_FIELD_BRD_STATUS",   "customfield_10101"),
    "feature_type": os.getenv("JIRA_FIELD_FEATURE_TYPE", "customfield_10102"),
}

# BRD 상태 → 승인 여부 매핑
BRD_STATUS_MAP = {
    "미해결":              "Pre-BRD",
    "BRD Submitted":      "Pending",
    "In Business Review": "Pending",
    "Revision Requested": "Pending",
    "HQ Discussion":      "Pending",
    "Confirmed":          "Approved",
    "진행 중":             "Approved",
    "해결됨":              "Approved",
    "Dropped":            "Rejected",
    "종료":               "Approved",
}

# Priority 점수 산정 대상 항목 (각 0 또는 1, 합산 0~5)
# 시급성(urgency)은 Fast Track 분류용이며 합산에서 제외
SCORE_KEYS_FOR_PRIORITY = [
    "business_performance",
    "customer_experience",
    "operational_efficiency",
    "global_reach",
    "platform_strategy",
]

# 지역 분류
EU_COUNTRIES = {
    "Italy", "Spain", "France", "Germany", "Netherlands",
    "Belgium", "Poland", "Portugal", "Sweden", "Norway",
    "Denmark", "Finland", "Austria", "Switzerland", "UK",
}
