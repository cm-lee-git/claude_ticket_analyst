import requests
from requests.auth import HTTPBasicAuth
from config import JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN, JIRA_PROJECTS, JIRA_FIELDS, BRD_STATUS_MAP, EU_COUNTRIES


class JiraClient:
    def __init__(self):
        self.base = f"{JIRA_BASE_URL}/rest/api/3"
        self.auth = HTTPBasicAuth(JIRA_EMAIL, JIRA_API_TOKEN)
        self.headers = {"Accept": "application/json"}

    def _get(self, path: str, params: dict = None) -> dict:
        r = requests.get(f"{self.base}{path}", auth=self.auth, headers=self.headers, params=params)
        r.raise_for_status()
        return r.json()

    def list_fields(self) -> list[dict]:
        """사용 가능한 모든 필드 목록 반환 (커스텀 필드 ID 확인용)."""
        return self._get("/field")

    def get_new_improvement_tickets(self, extra_jql: str = "") -> list[dict]:
        """CCIPRJ, KCCIVOC, KEUVOCOP의 New/Improvement 티켓 전체 조회."""
        project_clause = ", ".join(f'"{p}"' for p in JIRA_PROJECTS)
        jql = f"project in ({project_clause}) AND issuetype in (New, Improvement, 신규, 개선) ORDER BY created DESC"
        if extra_jql:
            jql = f"({jql}) AND {extra_jql}"
        return self._search(jql)

    def _search(self, jql: str) -> list[dict]:
        fields = [
            "summary", "reporter", "created", "duedate", "status", "description",
            JIRA_FIELDS["country"], JIRA_FIELDS["brd_status"], JIRA_FIELDS["feature_type"],
        ]
        results, start = [], 0
        while True:
            data = self._get("/search", params={
                "jql": jql,
                "startAt": start,
                "maxResults": 100,
                "fields": ",".join(fields),
            })
            issues = data.get("issues", [])
            results.extend(issues)
            start += len(issues)
            if start >= data.get("total", 0):
                break
        return [self._normalize(i) for i in results]

    def _normalize(self, issue: dict) -> dict:
        f = issue["fields"]
        country_raw = (f.get(JIRA_FIELDS["country"]) or {}).get("value", "")
        brd_raw = (f.get(JIRA_FIELDS["brd_status"]) or {}).get("value", "미해결")
        return {
            "key":            issue["key"],
            "summary":        f.get("summary", ""),
            "reporter":       (f.get("reporter") or {}).get("displayName", ""),
            "created":        (f.get("created") or "")[:10],
            "due_date":       f.get("duedate") or "",
            "status":         (f.get("status") or {}).get("name", ""),
            "description":    self._extract_text(f.get("description")),
            "country":        country_raw,
            "region":         self._classify_region(country_raw),
            "brd_status_raw": brd_raw,
            "brd_approval":   BRD_STATUS_MAP.get(brd_raw, "Pre-BRD"),
            "feature_type":   (f.get(JIRA_FIELDS["feature_type"]) or {}).get("value", ""),
        }

    @staticmethod
    def _classify_region(country: str) -> str:
        if not country:
            return "HQ"
        c = country.strip()
        if c in ("KR", "Korea"):
            return "KR"
        if c in ("All", "Global", "HQ"):
            return "HQ"
        if c in EU_COUNTRIES:
            return "EU"
        return "HQ"

    @staticmethod
    def _extract_text(doc) -> str:
        """Jira ADF(Atlassian Document Format) → 평문 변환."""
        if not doc:
            return ""
        if isinstance(doc, str):
            return doc
        texts = []
        def walk(node):
            if isinstance(node, dict):
                if node.get("type") == "text":
                    texts.append(node.get("text", ""))
                for child in node.get("content", []):
                    walk(child)
        walk(doc)
        return " ".join(texts).strip()
