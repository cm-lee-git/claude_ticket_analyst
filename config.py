import os
from dotenv import load_dotenv

load_dotenv()

ATLASSIAN_BASE_URL = "https://ihqdf.atlassian.net"
ATLASSIAN_EMAIL = os.getenv("ATLASSIAN_EMAIL")
ATLASSIAN_API_TOKEN = os.getenv("ATLASSIAN_API_TOKEN")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

JIRA_PROJECTS = ["CCIPRJ", "KCCIVOC", "KEUVOCOP"]

CONFLUENCE_PARENT_PAGE_ID = "68222989"

# 각 문서 페이지 제목 (부분 일치로 탐색)
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
}

# Scoring 가중치
SCORE_WEIGHTS = {
    "urgency":               0.25,
    "business_performance":  0.20,
    "customer_experience":   0.20,
    "operational_efficiency":0.15,
    "global_reach":          0.10,
    "platform_strategy":     0.10,
}

# 지역 분류
EU_COUNTRIES = {
    "Italy", "Spain", "France", "Germany", "Netherlands",
    "Belgium", "Poland", "Portugal", "Sweden", "Norway",
    "Denmark", "Finland", "Austria", "Switzerland", "UK",
}
