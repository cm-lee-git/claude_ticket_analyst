import requests
from requests.auth import HTTPBasicAuth
from lxml import etree
from config import ATLASSIAN_BASE_URL, ATLASSIAN_EMAIL, ATLASSIAN_API_TOKEN, CONFLUENCE_PARENT_PAGE_ID, DOC_TITLE_KEYWORDS


class ConfluenceClient:
    def __init__(self):
        self.base = f"{ATLASSIAN_BASE_URL}/wiki/api/v2"
        self.auth = HTTPBasicAuth(ATLASSIAN_EMAIL, ATLASSIAN_API_TOKEN)
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
                # "(Kia) 신규/개선" 제외, "신규/개선" 포함
                if keyword in title and "(Kia)" not in title:
                    self._page_cache[doc_key] = page
                    return page
            else:
                if keyword in title:
                    self._page_cache[doc_key] = page
                    return page
        raise ValueError(f"페이지를 찾을 수 없음: {doc_key} (keyword='{keyword}')")

    def get_page_storage(self, page_id: str) -> tuple[str, int, str]:
        """페이지 storage XML, 버전 번호, 제목을 반환."""
        data = self._get(f"/pages/{page_id}", params={"body-format": "storage"})
        xml = data["body"]["storage"]["value"]
        version = data["version"]["number"]
        title = data["title"]
        return xml, version, title

    def update_page(self, page_id: str, title: str, new_xml: str, version: int, message: str = "Automated update") -> dict:
        return self._put(f"/pages/{page_id}", {
            "id": page_id,
            "status": "current",
            "title": title,
            "body": {"representation": "storage", "value": new_xml},
            "version": {"number": version + 1, "message": message},
        })

    # ──────────────────────────────────────────────
    # XML / 표 조작 유틸
    # ──────────────────────────────────────────────

    @staticmethod
    def parse_xml(xml: str) -> etree._Element:
        parser = etree.XMLParser(recover=True)
        return etree.fromstring(f"<root>{xml}</root>".encode(), parser)

    @staticmethod
    def serialize_xml(root: etree._Element) -> str:
        inner = b"".join(etree.tostring(child, encoding="unicode").encode() for child in root)
        return inner.decode()

    @staticmethod
    def find_tables(root: etree._Element) -> list[etree._Element]:
        return root.findall(".//table")

    @staticmethod
    def get_cell_text(cell: etree._Element) -> str:
        return "".join(cell.itertext()).strip()

    @staticmethod
    def set_cell_text(cell: etree._Element, text: str):
        """셀의 모든 자식 제거 후 텍스트로 교체. 병합 셀 속성은 유지."""
        # 기존 자식 제거
        for child in list(cell):
            cell.remove(child)
        cell.text = None
        # <p> 태그로 감싸서 삽입 (Confluence 표준)
        p = etree.SubElement(cell, "p")
        p.text = text

    @staticmethod
    def append_row(tbody: etree._Element, cells: list[str], tag: str = "td"):
        tr = etree.SubElement(tbody, "tr")
        for text in cells:
            cell = etree.SubElement(tr, tag)
            p = etree.SubElement(cell, "p")
            p.text = text
        return tr

    @staticmethod
    def find_table_by_header(tables: list[etree._Element], header_keyword: str) -> etree._Element | None:
        """첫 번째 행(헤더)에 keyword가 포함된 표를 반환."""
        for table in tables:
            first_row = table.find(".//tr")
            if first_row is not None:
                row_text = "".join(first_row.itertext())
                if header_keyword in row_text:
                    return table
        return None
