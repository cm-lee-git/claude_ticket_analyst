import re
import requests
from requests.auth import HTTPBasicAuth
from config import CONFLUENCE_BASE_URL, CONFLUENCE_EMAIL, CONFLUENCE_API_TOKEN, CONFLUENCE_PARENT_PAGE_ID, DOC_TITLE_KEYWORDS


class ConfluenceClient:
    def __init__(self):
        self.base = f"{CONFLUENCE_BASE_URL}/wiki/api/v2"
        self.auth = HTTPBasicAuth(CONFLUENCE_EMAIL, CONFLUENCE_API_TOKEN)
        self.headers = {"Accept": "application/json", "Content-Type": "application/json"}
        self._page_cache: dict[str, dict] = {}

    def _get(self, path: str, params: dict = None) -> dict:
        r = requests.get(f"{self.base}{path}", auth=self.auth, headers=self.headers, params=params)
        r.raise_for_status()
        return r.json()

    def _put(self, path: str, payload: dict) -> dict:
        r = requests.put(f"{self.base}{path}", auth=self.auth, headers=self.headers, json=payload)
        r.raise_for_status()
        return r.json()

    def get_child_pages(self, parent_id: str = CONFLUENCE_PARENT_PAGE_ID) -> list[dict]:
        data = self._get(f"/pages/{parent_id}/children", params={"limit": 50})
        return data.get("results", [])

    def find_page(self, doc_key: str) -> dict:
        """doc_key ('doc1'|'doc2'|'doc3') 에 해당하는 페이지 메타 반환."""
        if doc_key in self._page_cache:
            return self._page_cache[doc_key]
        keyword = DOC_TITLE_KEYWORDS[doc_key]
        children = self.get_child_pages()
        for page in children:
            title = page.get("title", "")
            if doc_key == "doc2":
                if keyword in title and "(Kia)" not in title:
                    self._page_cache[doc_key] = page
                    return page
            else:
                if keyword in title:
                    self._page_cache[doc_key] = page
                    return page
        raise ValueError(f"페이지를 찾을 수 없음: {doc_key} (keyword='{keyword}')")

    def get_page_storage(self, page_id: str) -> tuple[str, int, str]:
        """페이지 Storage Format HTML, 버전 번호, 제목을 반환."""
        data = self._get(f"/pages/{page_id}", params={"body-format": "storage"})
        html = data["body"]["storage"]["value"]
        version = data["version"]["number"]
        title = data["title"]
        return html, version, title

    def update_page(self, page_id: str, title: str, new_html: str, version: int, message: str = "Automated update") -> dict:
        return self._put(f"/pages/{page_id}", {
            "id": page_id,
            "status": "current",
            "title": title,
            "body": {"representation": "storage", "value": new_html},
            "version": {"number": version + 1, "message": message},
        })

    # ──────────────────────────────────────────────
    # Placeholder 기반 구역 교체 (Step 3 핵심 로직)
    # ──────────────────────────────────────────────

    @staticmethod
    def replace_section(html: str, marker: str, new_content: str) -> str:
        """<!-- MARKER_START --> ~ <!-- MARKER_END --> 사이를 new_content로 덮어씁니다."""
        pattern = rf'(<!-- {marker}_START -->).*?(<!-- {marker}_END -->)'
        replacement = rf'\1\n{new_content}\n\2'
        result = re.sub(pattern, replacement, html, flags=re.DOTALL)
        if result == html:
            raise ValueError(
                f"마커 '{marker}_START / {marker}_END'를 페이지에서 찾을 수 없습니다.\n"
                f"Confluence 페이지 편집기에서 해당 마커가 삽입되어 있는지 확인하세요."
            )
        return result

    @staticmethod
    def append_to_section(html: str, marker: str, new_content: str) -> str:
        """<!-- MARKER_START --> ~ <!-- MARKER_END --> 사이의 기존 내용 끝에 new_content를 추가합니다 (히스토리 누적용)."""
        pattern = rf'(<!-- {marker}_START -->.*?)(<!-- {marker}_END -->)'
        replacement = rf'\1{new_content}\n\2'
        result = re.sub(pattern, replacement, html, flags=re.DOTALL)
        if result == html:
            raise ValueError(
                f"마커 '{marker}_START / {marker}_END'를 페이지에서 찾을 수 없습니다.\n"
                f"Confluence 페이지 편집기에서 해당 마커가 삽입되어 있는지 확인하세요."
            )
        return result
