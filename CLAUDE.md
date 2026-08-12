# CCI Ticket Screener — 프로젝트 컨텍스트

## 1. 프로젝트 개요

INNOCEAN GBCXD팀이 운영하는 **CCI Digital Platform 티켓 자동 분석 봇**.
Jira에서 Kia 관련 신규/개선 티켓을 가져와 Claude로 분석하고, Confluence 문서를 자동 생성한다.

- **Jira 인스턴스**: `https://hmg.atlassian.net` (프로젝트: KCCIVOC, KEUVOCOP)
- **Confluence 인스턴스**: `https://ihqdf.atlassian.net`
- **Claude API**: h-chat 사내 프록시 (`ANTHROPIC_BASE_URL`로 설정, api.anthropic.com 직접 호출 불가)
- **자동화**: GitHub Actions 사용 안 함 (h-chat이 사내망 전용이라 외부 접근 불가) → Windows 작업 스케줄러로 로컬 실행

---

## 2. 실행 방법

```bash
# Doc1 업데이트 (KKR OneApp 주간 보고 — 전체 재생성)
python main.py --doc1

# Doc1 일일 업데이트 (당일 신규 티켓 행 추가만)
python main.py --doc1-daily

# Doc2 업데이트 (신규/개선 전체 현황 — 전체 재생성)
python main.py --doc2

# Doc2 일일 업데이트 (신규 티켓 없으면 자동 종료)
python main.py --doc2-daily

# Doc2-1 스냅샷 (회차 마감일에만 Confluence 저장)
python main.py --snapshot

# 알림 이메일 발송 (Jira 변경사항)
python main.py --notify

# 전체 업데이트 (Doc1 + Doc2)
python main.py --all
```

**로컬 테스트 (Confluence 미반영)**:
```bash
python test_local.py --doc1 --dry-run
```

---

## 3. 자동화 스케줄 (Windows 작업 스케줄러)

| 작업 이름 | 배치파일 | 실행 시점 |
|---|---|---|
| CCI_Doc1_Weekly | `run_doc1.bat` | 매주 월요일 11:00 (전체 재생성) |
| CCI_Doc1_Daily | `run_doc1_daily.bat` | 화~금 11:00 (신규 행 추가) |
| CCI_Doc2_Weekly | `run_doc2.bat` | 매주 월요일 10:00 (전체 재생성) |
| CCI_Doc2_Daily | `run_doc2_daily.bat` | 평일 16:00 (신규 있으면 업데이트) |
| CCI_Snapshot_Daily | `run_snapshot.bat` | 평일 18:00 (회차 마감일이면 Doc2-1 생성) |
| CCI_Notify | `run_notify.bat` | 평일 16:00 (Jira 변경 알림 이메일) |

로그: `logs/` 폴더에 날짜별 저장

> GitHub Actions 워크플로우 파일(`.github/workflows/`)은 수동 실행(`workflow_dispatch`)만 남겨두고 스케줄은 비활성화 상태.

---

## 4. 파일 구조

```
cci-analyst/
├── main.py              # CLI 진입점 (--doc1 / --doc1-daily / --doc2 / --doc2-daily / --snapshot / --notify / --all)
├── config.py            # 환경변수, Jira/Confluence 설정, BRD 상태 매핑
├── jira_client.py       # Jira API 클라이언트 (티켓 조회, description 수신)
├── analyzer.py          # Claude API 호출 → 티켓 분석 (summary/background/problem/scores)
├── confluence_client.py # Confluence API 클라이언트 (페이지 생성/업데이트/프로퍼티)
├── cycle.py             # 회차(Cycle) 계산 (앵커: 2026-06-08, 2주 단위)
├── doc1_updater.py      # Doc1 HTML 빌드 및 Confluence 페이지 생성
├── doc2_updater.py      # Doc2 업데이트 로직
├── snapshot.py          # Doc2-1 회차별 마감 히스토리 스냅샷
├── notify.py            # Jira 변경 알림 이메일 (Outlook COM)
├── test_local.py        # 로컬 dry-run 테스트 (DryRunConfluenceClient)
├── run_doc1.bat         # Doc1 전체 재생성 (월요일 11:00)
├── run_doc1_daily.bat   # Doc1 일일 신규 추가 (화~금 11:00)
├── run_doc2.bat         # Doc2 전체 재생성 (월요일 10:00)
├── run_doc2_daily.bat   # Doc2 일일 업데이트 (평일 16:00)
├── run_snapshot.bat     # Doc2-1 스냅샷 (평일 18:00, 마감일에만 실행)
├── run_notify.bat       # 알림 이메일 (평일 16:00)
├── setup_tasks.ps1      # Windows 작업 스케줄러 설치
├── cycle_snapshots.json # 회차별 마감 시점 데이터 (누적)
├── notify_state.json    # 마지막 알림 발송 시각 추적
└── .env                 # 인증 정보 (git 미포함)
```

---

## 5. 티켓 조회 필터 규칙 (반드시 유지)

모든 문서(doc1/doc2)에 동일하게 적용:

1. **날짜**: `created >= "2026-01-01"` 이후 티켓만
2. **프로젝트**: KCCIVOC(KR), KEUVOCOP(EU)
3. **이슈 타입**: 신규/개선, Urgent Request
4. **브랜드 (OR 조건)**:
   - `customfield_10183` (대상 브랜드): Kia, Common
   - `customfield_10585` (Brand): KMC, ALL

`jira_client.py`의 `get_new_improvement_tickets()` JQL 참고:
```python
base = (
    'project in (KCCIVOC, KEUVOCOP) '
    'AND issuetype in ("신규/개선", "Urgent Request") '
    'AND (customfield_10183 in ("Kia", "Common") '
    '  OR customfield_10585 in ("KMC", "ALL"))'
)
```

---

## 6. Confluence 문서 구조

| 키 | 페이지 ID | 역할 |
|---|---|---|
| `doc1` | 77529216 | AI 생성: KKR OneApp 주간 보고 (부모 폴더) |
| `doc2` | 78020650 | AI 생성: 신규/개선 티켓 스크리닝 및 관리 |
| `doc21` | 77922419 | AI 생성: 회차별 마감 히스토리 (Doc2-1 부모 폴더) |

**Doc1 생성 방식**: 실행할 때마다 타임스탬프가 붙은 **새 페이지**를 생성
- 제목 형식: `MM-DD HH:MM KKR OneApp 주간 보고 (AI 생성)`
- 부모: `77529216` (AI 생성 폴더)
- 페이지 설정: full-width (`content-appearance-published/draft = "full-width"`)

**Doc2-1 생성 방식**: 회차 마감일(금요일) 18:00에만 **새 페이지** 자동 생성
- 제목 형식: `MM-DD HH:MM 회차별 마감 히스토리 (AI 생성)`
- 부모: `77922419` (Doc2-1 폴더)
- 트리거: `snapshot.py` (매 회차 마지막 금요일 18:00 KST)

---

## 7. 스코어링 프레임워크 (GBCXD New/Improvement Prioritization)

### 점수 도메인 (각 0~5):
- `urgency`: 대규모 장애 / 법규 대응 / 리더십 결정 → Fast Track 분류용, Priority 합산 제외
- `business_performance`: 전환율·리드·구매 유도 직접 영향
- `customer_experience`: 반복 VoC / 행동 데이터 기반 고객 불편
- `operational_efficiency`: 수기 반복 제거 / 비용 절감 수치 확인
- `global_reach`: MAU 2M+ AND 수혜 국가 비율 50%+ 동시 충족
- `platform_strategy`: 권역 KPI 연계 (KR: 제어/정비/충전, EU: 다운로드/가입, Global: Non-CCS/CCS)

**Priority 점수** = 가중 평균:
urgency(×0.25) + business_performance(×0.20) + customer_experience(×0.20) + operational_efficiency(×0.15) + global_reach(×0.10) + platform_strategy(×0.10)

### BRD 승인 상태 매핑 (Post-BRD 티켓에만 적용):

**Approved:** Confirmed, HQ Discussion, In Business Review, 진행 중, QA Sign-Off, Re-Opened, 종료, Deployed, Dropped, RESOLVE, 해결됨

**보류 (Hold):** BRD Submitted, Create Issue, 미해결, Reopen, Revision Requested

> 보류 상태라도 분석 결과 R1~R4 해당 시 → 반려로 최종 분류

### 지역 분류:
- **KR**: KCCIVOC 프로젝트 + country ≠ "Global"
- **EU**: KEUVOCOP 프로젝트 + country ≠ "Global"
- **HQ**: country = "Global" (프로젝트 무관)

---

## 8. Doc1 표 구조

**Pre-BRD (BRD 프로세스 적용 이전)**:
- `cycle_number == 0` 티켓 (2026-06-08 앵커 이전 생성)
- `created` 오름차순 정렬

**Post-BRD (BRD 프로세스 적용 이후)**:
- `cycle_number >= 1` 티켓
- `cycle_number` 오름차순 → `created` 오름차순 정렬

**컬럼**: # | Cycle | Key | Ticket Summary | Reporter | Created | Due date | 내용 | 항목 분포(×6) | Priority 점수 | BRD 승인 여부

**내용 셀 형식**:
```
<Status>
현재 처리 상태 요약

<Summary>
• 1~2문장 요약

<배경>
• 포인트1

<문제>
• 포인트1

<기존 기능 개선 / 신규 기능>
• 포인트1
```

---

## 9. 환경 설정

`.env` 파일 필수 항목:
```
JIRA_EMAIL=...
JIRA_API_TOKEN=...
CONFLUENCE_EMAIL=...
CONFLUENCE_API_TOKEN=...
ANTHROPIC_API_KEY=...       # h-chat API 키
ANTHROPIC_BASE_URL=https://h-chat-api.autoever.com/claude-code/v2
JIRA_FIELD_COUNTRY=customfield_XXXXX
JIRA_FIELD_BRD_STATUS=customfield_XXXXX
JIRA_FIELD_FEATURE_TYPE=customfield_XXXXX
```

> `ANTHROPIC_BASE_URL`이 설정되면 Anthropic SDK가 자동으로 h-chat 엔드포인트를 사용한다. 직접 Anthropic API 키를 쓰려면 이 변수를 제거하면 된다.

---

## 10. 텍스트 출력 규칙

- 텍스트 필드(summary, background, problem 등): **한국어**
- 필드 키, JSON 구조: **영어**
