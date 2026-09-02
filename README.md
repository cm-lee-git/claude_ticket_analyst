# CCI Ticket Analyst

KCCIVOC · KEUVOCOP Jira 티켓을 자동으로 분석하고 Confluence 문서를 업데이트하는 자동화 도구입니다.
사내 Claude 프록시(h-chat)를 사용하므로 **사내망에서만 동작**하며, Windows 작업 스케줄러로 자동 실행됩니다.

---

## 자동화 대상 문서

| 문서 | Confluence 폴더 ID | 업데이트 주기 |
|---|---|---|
| 1) KKR OneApp 주간 보고 (Doc1) | 77529216 | 월 11:00 (전체 재생성) / 화~금 11:00 (신규 티켓 추가) |
| 2) 신규/개선 전체 현황 (Doc2) | 78020650 | 월 10:00 (전체 재생성) / 평일 16:00 (신규 티켓 감지 시 업데이트) |
| 2-1) 회차별 마감 히스토리 | 77922419 | 평일 18:00 (회차 마감일에만 스냅샷 생성) |
| 이메일 알림 (notify) | — | 평일 16:00 (상태 변경·신규 댓글 감지 시 발송) |

---

## 처음 세팅

### Step 1. 패키지 설치

```bash
cd cci-analyst
pip install -r requirements.txt
```

### Step 2. .env 파일 작성

`.env.example`을 복사하여 `.env`를 만들고 아래 항목을 입력합니다:

```
JIRA_EMAIL=...                 # Atlassian 로그인 이메일
JIRA_API_TOKEN=...             # Atlassian API 토큰 (hmg.atlassian.net)
CONFLUENCE_EMAIL=...           # Atlassian 로그인 이메일 (ihqdf.atlassian.net)
CONFLUENCE_API_TOKEN=...       # Atlassian API 토큰 (ihqdf.atlassian.net)
ANTHROPIC_API_KEY=...          # h-chat API 키
ANTHROPIC_BASE_URL=https://h-chat-api.autoever.com/claude-code/v2
```

> Jira와 Confluence는 인스턴스가 다르므로 각각 별도 토큰이 필요합니다.
> Atlassian API 토큰 발급: https://id.atlassian.com/manage-profile/security/api-tokens

### Step 3. Jira 커스텀 필드 ID 확인 (최초 1회)

```bash
python main.py --list-fields
```

출력 목록에서 Country · BRD Status · Feature Type에 해당하는 `customfield_XXXXX` 값을 확인합니다.
기본값은 `config.py`에 하드코딩되어 있으며, 다를 경우 `.env`에서 오버라이드합니다:

```
JIRA_FIELD_COUNTRY=customfield_10175
JIRA_FIELD_BRD_STATUS=customfield_10101
JIRA_FIELD_FEATURE_TYPE=customfield_10102
```

### Step 4. 동작 확인

```bash
python main.py --doc1        # Doc1 즉시 실행
python main.py --doc2        # Doc2 즉시 실행
python main.py --snapshot    # 스냅샷 즉시 실행 (회차 마감일이 아니면 자동 종료)
```

### Step 5. 작업 스케줄러 등록

`setup_tasks.bat`을 더블클릭하거나 cmd에서 실행합니다 (관리자 권한 불필요):

```bat
setup_tasks.bat
```

등록되는 작업 목록:

| 작업 이름 | 실행 시점 |
|---|---|
| CCI_Doc1_Weekly | 매주 월요일 11:00 |
| CCI_Doc1_Daily | 매주 화~금 11:00 |
| CCI_Doc2_Weekly | 매주 월요일 10:00 |
| CCI_Doc2_Daily | 평일 매일 16:00 |
| CCI_Snapshot_Daily | 평일 매일 18:00 |
| CCI_Notify | 평일 매일 16:00 |

---

## 이후 운영

- **자동 실행**: 컴퓨터가 켜져 있고 로그인된 상태여야 합니다. 절전 모드는 작업이 지연될 수 있습니다.
- **수동 실행**: 터미널에서 `python main.py --doc1` 등을 직접 실행합니다.
- **로그 확인**: `logs/` 폴더에 날짜별 로그 파일이 저장됩니다.
- **스케줄 변경**: `setup_tasks.bat`을 수정 후 재실행하거나, Windows 작업 스케줄러에서 직접 수정합니다.
- **이메일 수신자 변경**: `notify.py` 상단 `RECIPIENTS` 딕셔너리를 수정합니다.

---

## 파일 구조

```
cci-analyst/
├── main.py                      # CLI 진입점
├── config.py                    # 환경변수, Jira/Confluence 설정, BRD 상태 매핑
├── jira_client.py               # Jira API 클라이언트
├── analyzer.py                  # Claude API 호출 → 티켓 분석
├── confluence_client.py         # Confluence API 클라이언트
├── cycle.py                     # 회차(Cycle) 계산 (앵커: 2026-06-08, 2주 단위)
├── doc1_updater.py              # Doc1 빌드
├── doc2_updater.py              # Doc2 빌드
├── snapshot.py                  # Doc2-1 스냅샷
├── notify.py                    # 이메일 알림
├── run_doc1.bat                 # Doc1 월요일 실행
├── run_doc1_daily.bat           # Doc1 화~금 실행
├── run_doc2.bat                 # Doc2 월요일 실행
├── run_doc2_daily.bat           # Doc2 평일 실행
├── run_snapshot.bat             # 스냅샷 실행
├── run_notify.bat               # 알림 실행
├── setup_tasks.bat              # 작업 스케줄러 일괄 등록
├── setup_tasks.ps1              # PowerShell 버전 등록
├── ticket_overrides.json        # 티켓별 수동 오버라이드
├── notify_state.json            # 알림 상태 영속 데이터
├── tickets_analyzed_latest.json # 마지막 분석 결과 캐시
├── cycle_snapshots.json         # 회차 스냅샷 영속 데이터
├── logs/                        # 실행 로그
└── .env                         # 인증 정보 (git 미포함)
```
