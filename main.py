"""
CCI Ticket Analyst — 메인 실행 파일

사용법:
  python main.py --doc1          # Doc1 업데이트 (KKR 주간 보고)
  python main.py --doc2          # Doc2 업데이트 (신규/개선 전체 현황)
  python main.py --doc3          # Doc3 업데이트 ((Kia) 신규/개선)
  python main.py --all           # 전체 문서 업데이트
  python main.py --list-fields   # Jira 커스텀 필드 ID 목록 출력 (초기 설정용)
"""
import argparse
import sys
from datetime import date

from config import JIRA_EMAIL, JIRA_API_TOKEN, CONFLUENCE_EMAIL, CONFLUENCE_API_TOKEN, ANTHROPIC_API_KEY
from cycle import get_cycle_number
from jira_client import JiraClient
from confluence_client import ConfluenceClient
from analyzer import analyze_tickets_batch
import doc1_updater
import doc2_updater
import doc3_updater


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


def _fetch_and_analyze() -> list[dict]:
    print("Jira 티켓 조회 중...")
    jira = JiraClient()
    tickets = jira.get_new_improvement_tickets()
    print(f"  → {len(tickets)}건 조회됨")

    # cycle_number 부여
    today = date.today()
    for t in tickets:
        created = date.fromisoformat(t["created"]) if t.get("created") else today
        t["cycle_number"] = get_cycle_number(created)

    print("Claude로 티켓 분석 중...")
    result = analyze_tickets_batch(tickets)
    print(f"  → {len(result)}건 분석 완료")
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
    _check_env()
    tickets = _fetch_and_analyze()
    doc1_updater.update(tickets, ConfluenceClient())


def cmd_doc2():
    _check_env()
    tickets = _fetch_and_analyze()
    doc2_updater.update(tickets, ConfluenceClient())


def cmd_doc3():
    _check_env()
    tickets = _fetch_and_analyze()
    doc3_updater.update(tickets, ConfluenceClient())


def cmd_all():
    _check_env()
    tickets = _fetch_and_analyze()
    client = ConfluenceClient()
    doc1_updater.update(tickets, client)
    doc2_updater.update(tickets, client)
    doc3_updater.update(tickets, client)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CCI Ticket Analyst")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--doc1",         action="store_true", help="Doc1 업데이트")
    group.add_argument("--doc2",         action="store_true", help="Doc2 업데이트")
    group.add_argument("--doc3",         action="store_true", help="Doc3 업데이트")
    group.add_argument("--all",          action="store_true", help="전체 문서 업데이트")
    group.add_argument("--list-fields",  action="store_true", help="Jira 커스텀 필드 목록 출력")
    args = parser.parse_args()

    if args.list_fields:
        cmd_list_fields()
    elif args.doc1:
        cmd_doc1()
    elif args.doc2:
        cmd_doc2()
    elif args.doc3:
        cmd_doc3()
    elif args.all:
        cmd_all()
