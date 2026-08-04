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
        project_clause = ", ".join(JIRA_PROJECTS)
        jql = f'project in ({project_clause}) AND issuetype in ("신규/개선", "Urgent Request") ORDER BY created DESC'
        if extra_jql:
            jql = f"({jql}) AND {extra_jql}"
        return self._search(jql)

    def _search(self, jql: str) -> list[dict]:
        # description은 /search/jql 미지원 → 개별 티켓 조회로 처리
        # /search/jql 은 nextPageToken 방식 페이지네이션 사용
        fields = [
            "summary", "reporter", "created", "duedate",
            "status", "issuetype",
            JIRA_FIELDS["country"],
        ]
        results = []
        payload = {"jql": jql, "maxResults": 100, "fields": fields}
        while True:
            r = requests.post(
                f"{self.base}/search/jql",
                auth=self.auth,
                headers={**self.headers, "Content-Type": "application/json"},
                json=payload,
            )
            r.raise_for_status()
            data = r.json()
            issues = data.get("issues", [])
            results.extend(issues)
            next_token = data.get("nextPageToken")
            if not next_token or not issues:
                break
            payload = {"jql": jql, "maxResults": 100, "fields": fields, "nextPageToken": next_token}
        return [self._normalize(i) for i in results]

    def get_description(self, issue_key: str) -> str:
        """티켓 개별 조회로 description 가져오기."""
        try:
            data = self._get(f"/issue/{issue_key}", params={"fields": "description"})
            text = self._extract_text(data["fields"].get("description"))
            chars = len(text)
            print(f"  [description] {issue_key}: {chars}자 {'OK' if chars > 0 else '⚠ 빈 값'}")
            return text
        except Exception as e:
            print(f"  [description] {issue_key}: 조회 실패 → {e}")
            return ""

    def _normalize(self, issue: dict) -> dict:
        f = issue["fields"]

        # 국가: customfield_10175 → 리스트 또는 단일 객체
        country_field = f.get(JIRA_FIELDS["country"])
        if isinstance(country_field, list):
            country_raw = country_field[0].get("value", "") if country_field else ""
        elif isinstance(country_field, dict):
            country_raw = country_field.get("value", "")
        else:
            country_raw = country_field or ""

        # BRD 상태: 표준 status 필드
        brd_raw = (f.get("status") or {}).get("name", "미해결")

        # Feature type: 표준 issuetype 필드
        feature_type = (f.get("issuetype") or {}).get("name", "")

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
            "feature_type":   feature_type,
            "description":    "",  # get_description()으로 별도 조회
        }

    @staticmethod
    def _classify_region(country: str) -> str:
        if not country:
            return "HQ"
        c = country.strip().upper()
        if c in ("KR", "KOREA"):
            return "KR"
        if c in ("ALL", "GLOBAL", "HQ"):
            return "HQ"
        eu = {c.upper() for c in EU_COUNTRIES}
        if c in eu:
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
