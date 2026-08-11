import requests
from requests.auth import HTTPBasicAuth
from config import JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN, JIRA_PROJECTS, JIRA_FIELDS, BRD_STATUS_MAP


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
        """Kia 관련 New/Improvement 티켓 조회.
        - CCIPRJ 제외: KCCIVOC, KEUVOCOP 두 프로젝트만
        - 브랜드 필터: brand 필드에 Kia 또는 Common 포함, 또는 brand 미기입(Kia 전용 프로젝트이므로)
        """
        # 브랜드 필터:
        # - 대상 브랜드(10183): Kia 또는 Common
        # - Brand(10585): KMC 또는 ALL
        # 둘 중 하나라도 해당하면 포함
        base = (
            'project in (KCCIVOC, KEUVOCOP) '
            'AND issuetype in ("신규/개선", "Urgent Request") '
            'AND ('
            'customfield_10183 in ("Kia", "Common") '
            'OR customfield_10585 in ("KMC", "ALL")'
            ')'
        )
        if extra_jql:
            base = f"{base} AND {extra_jql}"
        jql = f"{base} ORDER BY created DESC"
        tickets = self._search(jql)
        # Approved/Rejected 티켓에 대해 보류 경유 여부 확인 (승인전환·반려전환 판별)
        terminal = [t for t in tickets if t.get("brd_approval") == "Approved"]
        print(f"  [changelog] 이력 조회 대상: {len(terminal)}건")
        for t in terminal:
            t["was_pending"] = self._was_ever_pending(t["key"])
        for t in tickets:
            if "was_pending" not in t:
                t["was_pending"] = False
        return tickets

    def _search(self, jql: str) -> list[dict]:
        # POST /search/jql: 현행 Jira Cloud 표준 엔드포인트, nextPageToken 페이지네이션
        fields = [
            "summary", "reporter", "created",
            "status", "issuetype", "description",
            JIRA_FIELDS["country"],
            JIRA_FIELDS["brand"],    # 대상 브랜드: Kia, Common
            JIRA_FIELDS["brand2"],   # Brand: KMC, ALL
            JIRA_FIELDS["due_date"], # Due Date (customfield_10570)
        ]
        results = []
        payload = {"jql": jql, "maxResults": 50, "fields": fields}
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
            payload = {"jql": jql, "maxResults": 50, "fields": fields, "nextPageToken": next_token}
        total = data.get("total", len(results))
        print(f"  [search] 총 {len(results)}/{total}건 조회")
        return [self._normalize(i) for i in results]

    # BRD 보류 상태값 집합
    _PENDING_STATUSES = frozenset({
        "BRD Submitted", "In Business Review",
        "Revision Requested", "HQ Discussion",
    })

    def _was_ever_pending(self, issue_key: str) -> bool:
        """티켓이 한 번이라도 공식 보류(Pending) 상태를 거쳤으면 True."""
        try:
            data = self._get(f"/issue/{issue_key}/changelog")
            for history in data.get("values", []):
                for item in history.get("items", []):
                    if (item.get("field") == "status"
                            and item.get("toString") in self._PENDING_STATUSES):
                        return True
            return False
        except Exception as e:
            print(f"  [changelog] {issue_key}: 조회 실패 → {e}")
            return False

    def get_own_comments(self, issue_key: str, max_comments: int = 5) -> str:
        """티켓 자체 댓글 조회 — 리뷰어 보류·반려 사유 파악용 (R4, H 코드 보완)."""
        try:
            data = self._get(f"/issue/{issue_key}/comment",
                             params={"maxResults": max_comments, "orderBy": "-created"})
            comments = data.get("comments", [])
            if not comments:
                return ""
            parts = []
            for c in list(reversed(comments))[-max_comments:]:
                author = c.get("author", {}).get("displayName", "")
                created = c.get("created", "")[:10]
                text = self._extract_text(c.get("body"))[:300]
                if text:
                    parts.append(f"  [{created}] {author}: {text}")
            result = "\n".join(parts)
            print(f"  [own_comments] {issue_key}: {len(comments)}개 ({len(result)}자)")
            return result
        except Exception as e:
            print(f"  [own_comments] {issue_key}: 조회 실패 → {e}")
            return ""

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

        # 대상 브랜드 (10183): Kia, Common
        brand_field = f.get(JIRA_FIELDS["brand"])
        if isinstance(brand_field, list):
            brand_vals = [b.get("value", "") for b in brand_field if b.get("value")]
        elif isinstance(brand_field, dict):
            brand_vals = [brand_field.get("value", "")]
        else:
            brand_vals = []

        # Brand (10585): KMC, ALL
        brand2_field = f.get(JIRA_FIELDS["brand2"])
        if isinstance(brand2_field, list):
            brand2_vals = [b.get("value", "") for b in brand2_field if b.get("value")]
        elif isinstance(brand2_field, dict):
            brand2_vals = [brand2_field.get("value", "")]
        else:
            brand2_vals = []

        brand_vals = list(set(brand_vals + brand2_vals))  # 두 필드 합산

        summary = f.get("summary", "")
        project = issue["key"].split("-")[0]
        description = self._extract_text(f.get("description"))
        print(f"  [normalize] {issue['key']}: description {len(description)}자")
        return {
            "key":            issue["key"],
            "summary":        summary,
            "reporter":       (f.get("reporter") or {}).get("displayName", ""),
            "created":        (f.get("created") or "")[:10],
            "due_date":       f.get(JIRA_FIELDS["due_date"]) or "",
            "status":         (f.get("status") or {}).get("name", ""),
            "description":    description,
            "country":        country_raw,
            "brand":          brand_vals,
            "region":         self._classify_region(country_raw, project),
            "brd_status_raw": brd_raw,
            "brd_approval":   BRD_STATUS_MAP.get(brd_raw, "보류"),
            "feature_type":   feature_type,
        }

    @staticmethod
    def _classify_region(country: str, project: str = "") -> str:
        # country = "Global" → HQ (프로젝트 무관)
        if country and country.strip().lower() == "global":
            return "HQ"

        # 그 외 모두 프로젝트 기준
        p = project.upper()
        if p == "KCCIVOC":
            return "KR"
        if p == "KEUVOCOP":
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
