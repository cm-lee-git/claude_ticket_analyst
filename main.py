"""
CCI Ticket Analyst — 메인 실행 파일

사용법:
  python main.py --doc1          # Doc1 업데이트 (KKR 주간 보고)
  python main.py --doc2          # Doc2 업데이트 (신규/개선 전체 현황)
  python main.py --all           # 전체 문서 업데이트
  python main.py --list-fields   # Jira 커스텀 필드 ID 목록 출력 (초기 설정용)
"""
import argparse
import re
import sys
from datetime import date

# Windows cp949 콘솔에서 Unicode 출력 시 인코딩 오류 방지
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from config import JIRA_EMAIL, JIRA_API_TOKEN, CONFLUENCE_EMAIL, CONFLUENCE_API_TOKEN, ANTHROPIC_API_KEY
from cycle import get_cycle_number
from jira_client import JiraClient
from confluence_client import ConfluenceClient
from analyzer import analyze_tickets_batch
import doc1_updater
import doc2_updater
import snapshot as snapshot_module


def _check_env():
    missing = []
    if not JIRA_EMAIL:
        missing.append("JIRA_EMAIL")
    if not JIRA_API_TOKEN:
        missing.append("JIRA_API_TOKEN")
    if not CONFLUENCE_EMAIL:
        missing.append("CONFLUENCE_EMAIL")
    if not CONFLUENCE_API_TOKEN:
        missing.append("CONFLUENCE_API_TOKEN")
    if not ANTHROPIC_API_KEY:
        missing.append("ANTHROPIC_API_KEY")
    if missing:
        print(f"[오류] .env 파일에 다음 항목이 없습니다: {', '.join(missing)}")
        print("       .env.example 파일을 참고해서 .env를 만들어주세요.")
        sys.exit(1)


_TEST_SUMMARY_RE = re.compile(r'^\s*(brd\s*)?test\s*$', re.IGNORECASE)


def _is_test_ticket(t: dict) -> bool:
    """테스트/예시용 티켓 여부 판별."""
    # Jira 원본 제목이 "test" 또는 "BRD Test" 수준인 경우
    if _TEST_SUMMARY_RE.match(t.get("summary", "")):
        return True
    # Claude 분석 결과에서 "테스트 티켓"으로 명시한 경우
    if "테스트 티켓" in t.get("summary_ko", ""):
        return True
    return False


def _apply_test_filter(tickets: list[dict]) -> list[dict]:
    """테스트 티켓 제외 후 유효 티켓 반환. 제외 목록은 콘솔에 출력."""
    excluded = [t for t in tickets if _is_test_ticket(t)]
    if excluded:
        print(f"  → 테스트/예시 티켓 제외 ({len(excluded)}건):")
        for t in excluded:
            print(f"     - {t['key']}: {t.get('summary', '')}")
    return [t for t in tickets if not _is_test_ticket(t)]


def _fetch_and_analyze(extra_jql: str = "", save_path: str = "") -> list[dict]:
    import json, pathlib
    print("Jira 티켓 조회 중...")
    jira = JiraClient()
    tickets = jira.get_new_improvement_tickets(extra_jql=extra_jql)
    print(f"  → {len(tickets)}건 조회됨")

    # cycle_number 부여
    today = date.today()
    for t in tickets:
        created = date.fromisoformat(t["created"]) if t.get("created") else today
        t["cycle_number"] = get_cycle_number(created)

    print("Claude로 티켓 분석 중...")
    result = analyze_tickets_batch(tickets)
    print(f"  → {len(result)}건 분석 완료")

    # 테스트/예시 티켓 제외
    result = _apply_test_filter(result)

    # 분석 결과 저장 (다음 실행 시 재사용 가능)
    if save_path:
        pathlib.Path(save_path).write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"  → 분석 결과 저장: {save_path}")

    return result


def cmd_list_fields():
    _check_env()
    jira = JiraClient()
    fields = jira.list_fields()
    custom = [f for f in fields if f.get("custom")]
    print(f"{'ID':<30} {'이름'}")
    print("-" * 60)
    for f in sorted(custom, key=lambda x: x.get("id", "")):
        print(f"{f['id']:<30} {f.get('name', '')}")


def cmd_doc1():
    """월요일: 전체 티켓 재빌드 후 새 페이지 생성."""
    _check_env()
    tickets = _fetch_and_analyze(
        extra_jql='created >= "2026-01-01"',
        save_path="tickets_analyzed_latest.json",
    )
    doc1_updater.update(tickets, ConfluenceClient())


def cmd_doc1_daily():
    """화~금: 당일 생성된 신규 티켓만 기존 페이지에 추가."""
    _check_env()
    from datetime import timedelta
    today = date.today()
    tomorrow = today + timedelta(days=1)
    extra_jql = (
        f'created >= "2026-01-01" '
        f'AND created >= "{today.isoformat()}" '
        f'AND created < "{tomorrow.isoformat()}"'
    )
    tickets = _fetch_and_analyze(extra_jql=extra_jql)
    doc1_updater.append_new_tickets(tickets, ConfluenceClient())


def cmd_doc2():
    """월요일 10시: 전체 티켓 재빌드 후 새 페이지 생성."""
    _check_env()
    tickets = _fetch_and_analyze(
        extra_jql='created >= "2026-01-01"',
        save_path="tickets_analyzed_latest.json",
    )
    doc2_updater.update(tickets, ConfluenceClient())


def cmd_doc2_daily():
    """월 16시, 화~금 16시: 당일 신규 티켓 있으면 전체 분석 + 기존 페이지 업데이트."""
    _check_env()
    import json, pathlib
    from datetime import timedelta

    today = date.today()
    tomorrow = today + timedelta(days=1)
    today_jql = (
        f'created >= "{today.isoformat()}" '
        f'AND created < "{tomorrow.isoformat()}"'
    )
    full_jql = 'created >= "2026-01-01"'

    # 당일 신규 티켓 확인 (빠른 체크)
    from jira_client import JiraClient
    jira_check = JiraClient()
    new_today = jira_check.get_new_improvement_tickets(
        extra_jql=f'{today_jql}'
    )
    if not new_today:
        print("[Doc2-Daily] 당일 신규 티켓 없음 → 종료")
        return
    print(f"[Doc2-Daily] 당일 신규 티켓 {len(new_today)}건 감지 → 전체 분석 시작")

    # 전체 분석 (신규 티켓 분석 비용 감수, 정확성 우선)
    all_tickets = _fetch_and_analyze(
        extra_jql=full_jql,
        save_path="tickets_analyzed_latest.json",
    )
    doc2_updater.update_with_new_tickets(all_tickets, ConfluenceClient())


def cmd_snapshot(force_cycle=None):
    """회차 마감일 18:00 스냅샷 — 오늘이 마감일이 아니면 자동 종료."""
    _check_env()
    snapshot_module.take_snapshot(force_cycle=force_cycle)


def cmd_all():
    _check_env()
    tickets = _fetch_and_analyze(
        extra_jql='created >= "2026-01-01"',
        save_path="tickets_analyzed_latest.json",
    )
    client = ConfluenceClient()
    doc1_updater.update(tickets, client)
    doc2_updater.update(tickets, client)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CCI Ticket Analyst")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--doc1",         action="store_true", help="Doc1 월요일 전체 재생성")
    group.add_argument("--doc1-daily",   action="store_true", help="Doc1 화~금 당일 신규 티켓 추가")
    group.add_argument("--snapshot",     action="store_true", help="회차별 마감 히스토리 스냅샷 (회차 마감일 18시)")
    parser.add_argument("--force-cycle", type=int, default=None, metavar="N",
                        help="--snapshot 테스트용: 특정 회차 번호 강제 지정 (기본: 오늘 날짜 자동 판별)")
    group.add_argument("--doc2",         action="store_true", help="Doc2 월요일 전체 재생성")
    group.add_argument("--doc2-daily",   action="store_true", help="Doc2 월16시·화~금16시 신규 티켓 업데이트")
    group.add_argument("--all",          action="store_true", help="전체 문서 업데이트 (Doc1+Doc2)")
    group.add_argument("--list-fields",  action="store_true", help="Jira 커스텀 필드 목록 출력")
    args = parser.parse_args()

    if args.list_fields:
        cmd_list_fields()
    elif args.doc1:
        cmd_doc1()
    elif args.doc1_daily:
        cmd_doc1_daily()
    elif args.snapshot:
        cmd_snapshot(force_cycle=args.force_cycle)
    elif args.doc2:
        cmd_doc2()
    elif args.doc2_daily:
        cmd_doc2_daily()
    elif args.all:
        cmd_all()
