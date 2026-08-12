# CCI Ticket Analyst

KCCIVOC, KEUVOCOP의 Jira 티켓을 자동으로 분석하고 Confluence 문서를 업데이트하는 자동화 도구입니다.

---

## 자동화 대상 문서

| 문서 | 업데이트 주기 |
|---|---|
| KKR OneApp 주간 보고 (Doc1) | 매주 월요일 11:00 (전체 재생성) + 화~금 11:00 (신규 추가) |
| 신규/개선 전체 현황 (Doc2) | 매주 월요일 10:00 (전체 재생성) + 평일 16:00 (신규 업데이트) |
| 회차별 마감 히스토리 (Doc2-1) | 평일 18:00 자동 확인, 회차 마감일(금요일)에만 생성 |

---

## 사용 방법 (처음 세팅)

### Step 1. 이 템플릿으로 내 저장소 만들기

이 페이지 상단의 **"Use this template"** → **"Create a new repository"** 클릭  
→ 저장소 이름 입력 → **Private** 선택 → **Create repository**

### Step 2. API 키 3개 준비

| 키 | 발급 방법 |
|---|---|
| Atlassian API Token | [id.atlassian.com](https://id.atlassian.com/manage-profile/security/api-tokens) → Create API token |
| Anthropic API Key | [console.anthropic.com](https://console.anthropic.com/settings/keys) → Create Key |

### Step 3. .env 파일 작성

`.env.example`을 복사하여 `.env`를 만들고 아래 항목을 입력합니다:

```
JIRA_EMAIL=...                    # Atlassian 로그인 이메일
JIRA_API_TOKEN=...                # Atlassian API 토큰
CONFLUENCE_EMAIL=...              # Atlassian 로그인 이메일 (보통 JIRA_EMAIL과 동일)
CONFLUENCE_API_TOKEN=...          # Atlassian API 토큰 (보통 JIRA_API_TOKEN과 동일)
ANTHROPIC_API_KEY=...             # Claude API 키 (사내 h-chat 키 또는 직접 Anthropic 키)
ANTHROPIC_BASE_URL=...            # h-chat 사용 시 엔드포인트 URL (직접 Anthropic 사용 시 생략)
JIRA_FIELD_COUNTRY=customfield_XXXXX
JIRA_FIELD_BRD_STATUS=customfield_XXXXX
JIRA_FIELD_FEATURE_TYPE=customfield_XXXXX
```

> **참고**: 이 자동화는 사내 Claude 프록시(h-chat)를 사용합니다. h-chat은 사내망에서만 접근 가능하므로 GitHub Actions 대신 로컬 Windows 작업 스케줄러로 실행합니다.

### Step 4. Jira 커스텀 필드 ID 확인

로컬에서 아래 명령어를 실행하면 필드 목록이 출력됩니다.

```bash
# 1. 저장소 클론
git clone https://github.com/본인아이디/저장소이름.git
cd 저장소이름

# 2. 패키지 설치
pip install -r requirements.txt

# 3. .env 파일 생성
cp .env.example .env
# .env 파일을 열어 JIRA_EMAIL, JIRA_API_TOKEN 입력

# 4. 필드 목록 출력
python main.py --list-fields
```

출력된 목록에서 지역(Country), BRD 상태, 기능 유형에 해당하는 `customfield_XXXXX` 값을 찾아 Step 3의 Secrets에 입력합니다.

### Step 5. 동작 확인

터미널에서 직접 실행해 정상 동작을 확인합니다:

```bash
python main.py --doc1        # Doc1 즉시 실행
python main.py --doc2        # Doc2 즉시 실행
python main.py --snapshot    # Doc2-1 스냅샷 (회차 마감일에만 실제 생성)
```

---

## 이후 운영

- **자동 실행**: Windows 작업 스케줄러(`setup_tasks.ps1` 실행으로 등록)로 실행됩니다. **컴퓨터가 켜져 있고 로그인된 상태**여야 합니다.
- **수동 실행**: 터미널에서 `python main.py --doc1` 등을 직접 실행하거나, GitHub Actions 탭 → Run workflow로도 가능합니다. (단, GitHub Actions는 사내망 접근 불가로 Claude 분석은 동작하지 않으며 Jira 조회까지만 가능할 수 있습니다.)
- **로그 확인**: `logs/` 폴더에 날짜별 로그 파일이 저장됩니다.
- **스케줄 변경**: `setup_tasks.ps1`을 수정 후 관리자 권한으로 재실행하세요.
