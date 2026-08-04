"""
로컬 테스트 스크립트

사용법:
  python test_local.py --doc1 --dry-run        # HTML 파일만 생성
  python test_local.py --doc3 --dry-run
  python test_local.py --all  --dry-run
  python test_local.py --doc1                  # 실제 Confluence 쓰기
  python test_local.py --input other.json --doc1 --dry-run
"""
import argparse
import json
import pathlib
import re
import sys
from collections import Counter
from datetime import date

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE))

from config import BRD_STATUS_MAP
from cycle import get_cycle_number

# ── BRD 정규화 ─────────────────────────────────────────────────
_EXTRA_BRD = {
    "종료":              "Approved",
    "qa passed":         "Approved",
    "qа passed":         "Approved",   # 키릴 'а' 포함 케이스
    "stg deployed":      "Approved",
    "ready to deploy":   "Approved",
    "resolve":           "Approved",
    "create issue":      "Pre-BRD",
    "to-do":             "Pre-BRD",
    "hold":              "Pending",
    "stg qa":            "Pending",
}
_BRD_LOOKUP = {k.lower(): v for k, v in {**BRD_STATUS_MAP, **_EXTRA_BRD}.items()}


def _normalize_brd(raw: str) -> str:
    if not raw:
        return "Pre-BRD"
    hit = _BRD_LOOKUP.get(raw.strip().lower())
    return hit if hit else "Pre-BRD"


# ── 데이터 어댑터 ───────────────────────────────────────────────
def adapt_tickets(raw: list[dict]) -> list[dict]:
    """
    tickets_analyzed.json 형식 → updater가 기대하는 형식으로 변환.
    누락 필드는 합리적인 기본값으로 채움.
    """
    today = date.today()
    result = []
    for i, t in enumerate(raw):
        scores_raw = dict(t.get("scores", {}))

        # priority_score: scores 안에 있을 수도, 최상위에 있을 수도
        priority_score = float(scores_raw.pop("priority_score", 0)
                               or t.get("priority_score", 0) or 0)

        domain_keys = [
            "urgency", "business_performance", "customer_experience",
            "operational_efficiency", "global_reach", "platform_strategy",
        ]
        scores = {k: float(scores_raw.get(k, 0)) for k in domain_keys}

        brd_raw = t.get("brd_approval") or t.get("status") or ""
        brd_approval = _normalize_brd(brd_raw)

        created_str = (t.get("created") or str(today))[:10]
        try:
            created_date = date.fromisoformat(created_str)
        except ValueError:
            created_date = today

        result.append({
            "key":            t.get("key", f"TICKET-{i+1}"),
            "summary":        t.get("summary", ""),
            "summary_ko":     t.get("summary_ko") or t.get("summary", ""),
            "reporter":       t.get("reporter") or t.get("assignee") or "",
            "created":        created_str,
            "due_date":       t.get("due_date") or "",
            "status":         t.get("status", ""),
            "region":         t.get("region", "HQ"),
            "brd_status_raw": brd_raw,
            "brd_approval":   brd_approval,
            "feature_type":   t.get("issuetype") or t.get("feature_type", ""),
            "description":    t.get("description", ""),
            "background":     t.get("background", ""),
            "problem":        t.get("problem", ""),
            "feature":        t.get("feature", ""),
            "cycle_number":   get_cycle_number(created_date),
            "scores":         scores,
            "priority_score": round(priority_score, 2),
        })
    return result


# ── DryRunConfluenceClient ──────────────────────────────────────
_DOC2_MARKER_HTML = """\
<html><body>
<p>AUTO_SUMMARY_START</p><p>AUTO_SUMMARY_END</p>
<p>AUTO_TRACKING_START</p><p>AUTO_TRACKING_END</p>
<p>AUTO_TABLE_START</p><p>AUTO_TABLE_END</p>
<p>AUTO_PENDING_START</p><p>AUTO_PENDING_END</p>
<p>AUTO_MATRIX_START</p><p>AUTO_MATRIX_END</p>
<p>AUTO_KR_HISTORY_START</p><p>AUTO_KR_HISTORY_END</p>
<p>AUTO_EU_HISTORY_START</p><p>AUTO_EU_HISTORY_END</p>
<p>AUTO_HQ_HISTORY_START</p><p>AUTO_HQ_HISTORY_END</p>
<p>AUTO_HISTORY_START</p><p>AUTO_HISTORY_END</p>
</body></html>"""


class DryRunConfluenceClient:
    """Confluence 실제 쓰기 없이 로컬 HTML 파일로 저장."""

    def __init__(self, output_dir: str = "test_output"):
        self._out = pathlib.Path(output_dir)
        self._out.mkdir(parents=True, exist_ok=True)
        # 현재 페이지 상태 (연속 호출 시 이전 출력을 현재 상태로 사용)
        self._state: dict[str, str] = {
            "doc1": "<html><body></body></html>",
            "doc2": _DOC2_MARKER_HTML,
            "doc3": "<html><body></body></html>",
        }

    def find_page(self, doc_key: str) -> dict:
        return {"id": doc_key, "title": f"[DryRun] {doc_key}"}

    def get_page_storage(self, page_id: str) -> tuple[str, int, str]:
        html = self._state.get(page_id, "<html><body></body></html>")
        return html, 1, f"[DryRun] {page_id}"

    def update_page(self, page_id: str, title: str, new_html: str,
                    version: int, message: str = "") -> dict:
        out_path = self._out / f"{page_id}_output.html"
        out_path.write_text(new_html, encoding="utf-8")
        self._state[page_id] = new_html
        print(f"  [저장] {out_path}  ({len(new_html):,} chars)")
        return {}

    def get_space_id(self, page_id: str) -> str:
        return "dry-run-space"

    def create_page(self, parent_id: str, title: str, html: str) -> dict:
        safe = title.replace(":", "-").replace(" ", "_")
        out_path = self._out / f"{safe}.html"
        out_path.write_text(html, encoding="utf-8")
        print(f"  [새 페이지] {out_path}  ({len(html):,} chars)")
        return {"id": "dry-run-new-page"}

    # doc2_updater가 client.replace_section / append_to_section 으로 호출
    @staticmethod
    def replace_section(html: str, marker: str, new_content: str) -> str:
        pattern = rf'(<p>{marker}_START</p>).*?(<p>{marker}_END</p>)'
        result = re.sub(pattern, rf'\1\n{new_content}\n\2', html, flags=re.DOTALL)
        if result == html:
            # 마커 없으면 body 끝에 붙임 (dry-run 관용)
            result = html.replace("</body>", f"\n{new_content}\n</body>")
        return result

    @staticmethod
    def append_to_section(html: str, marker: str, new_content: str) -> str:
        pattern = rf'(<p>{marker}_START</p>.*?)(<p>{marker}_END</p>)'
        result = re.sub(pattern, rf'\1{new_content}\n\2', html, flags=re.DOTALL)
        if result == html:
            result = html.replace("</body>", f"\n{new_content}\n</body>")
        return result


# ── 통계 출력 ───────────────────────────────────────────────────
def print_stats(tickets: list[dict]):
    print(f"\n  총 {len(tickets)}건")
    print(f"  BRD    : {dict(Counter(t['brd_approval'] for t in tickets))}")
    print(f"  지역   : {dict(Counter(t['region'] for t in tickets))}")
    print(f"  회차   : {dict(sorted(Counter(t['cycle_number'] for t in tickets).items()))}")


# ── CLI ─────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="CCI Ticket Analyst — 로컬 테스트")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--doc1", action="store_true", help="Doc1 업데이트")
    group.add_argument("--doc2", action="store_true", help="Doc2 업데이트")
    group.add_argument("--doc3", action="store_true", help="Doc3 업데이트")
    group.add_argument("--all",  action="store_true", help="전체 문서 업데이트")
    parser.add_argument("--dry-run", action="store_true",
                        help="Confluence 쓰기 없이 HTML 파일로 저장 (기본: test_output/)")
    parser.add_argument("--input", default=None,
                        help="분석 완료 JSON 경로 (기본: ~/tickets_analyzed.json)")
    parser.add_argument("--out-dir", default="test_output",
                        help="dry-run HTML 저장 폴더")
    args = parser.parse_args()

    # ── 데이터 로드 ──────────────────────────────────────────────
    json_path = pathlib.Path(args.input) if args.input else pathlib.Path.home() / "tickets_analyzed.json"
    if not json_path.exists():
        print(f"[오류] 파일 없음: {json_path}")
        sys.exit(1)

    raw = json.loads(json_path.read_text(encoding="utf-8"))
    print(f"[로드] {json_path.name}  →  {len(raw)}건")
    tickets = adapt_tickets(raw)
    print_stats(tickets)

    # ── 클라이언트 선택 ──────────────────────────────────────────
    if args.dry_run:
        client = DryRunConfluenceClient(output_dir=args.out_dir)
        print(f"\n[DryRun 모드] HTML 출력 폴더: {args.out_dir}/")
    else:
        from config import CONFLUENCE_EMAIL, CONFLUENCE_API_TOKEN
        if not CONFLUENCE_EMAIL or not CONFLUENCE_API_TOKEN:
            print("[오류] CONFLUENCE_EMAIL / CONFLUENCE_API_TOKEN 미설정")
            sys.exit(1)
        from confluence_client import ConfluenceClient
        client = ConfluenceClient()
        print("\n[실제 Confluence 모드]")

    # ── 실행 ─────────────────────────────────────────────────────
    import doc1_updater, doc2_updater, doc3_updater

    if args.doc1 or args.all:
        print("\n--- Doc1 ---")
        doc1_updater.update(tickets, client)

    if args.doc2 or args.all:
        print("\n--- Doc2 ---")
        doc2_updater.update(tickets, client)

    if args.doc3 or args.all:
        print("\n--- Doc3 ---")
        doc3_updater.update(tickets, client)

    print("\n완료.")


if __name__ == "__main__":
    main()
