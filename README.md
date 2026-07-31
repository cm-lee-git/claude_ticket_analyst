# CCI Ticket Analyst

INNOCEAN GBCXD팀의 Jira 티켓을 자동으로 분석하고 Confluence 문서를 업데이트하는 자동화 도구입니다.

---

## 자동화 대상 문서

| 문서 | 업데이트 주기 |
|---|---|
| KKR OneApp 주간 보고 (Doc1) | 매주 월요일 10:00 |
| 신규/개선 전체 현황 (Doc2) | 평일 매일 10:00 |
| (Kia) 신규/개선 (Doc3) | 평일 매일 10:00 |

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

### Step 3. GitHub Secrets 등록

내 저장소 → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

아래 항목을 하나씩 등록합니다:

| Secret 이름 | 설명 |
|---|---|
| `ATLASSIAN_EMAIL` | Atlassian 로그인 이메일 |
| `ATLASSIAN_API_TOKEN` | Step 2에서 발급한 Atlassian API 토큰 |
| `ANTHROPIC_API_KEY` | Step 2에서 발급한 Anthropic API 키 |
| `JIRA_FIELD_COUNTRY` | Jira 지역 커스텀 필드 ID (Step 4 참고) |
| `JIRA_FIELD_BRD_STATUS` | Jira BRD 상태 커스텀 필드 ID (Step 4 참고) |
| `JIRA_FIELD_FEATURE_TYPE` | Jira 기능 유형 커스텀 필드 ID (Step 4 참고) |

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
# .env 파일을 열어 ATLASSIAN_EMAIL, ATLASSIAN_API_TOKEN 입력

# 4. 필드 목록 출력
python main.py --list-fields
```

출력된 목록에서 지역(Country), BRD 상태, 기능 유형에 해당하는 `customfield_XXXXX` 값을 찾아 Step 3의 Secrets에 입력합니다.

### Step 5. 동작 확인

내 저장소 → **Actions** 탭 → 워크플로우 선택 → **"Run workflow"** 버튼으로 수동 테스트

---

## 이후 운영

- **자동 실행**: Secrets만 등록하면 스케줄에 따라 GitHub 서버에서 자동 실행됩니다. 컴퓨터를 켜둘 필요 없습니다.
- **수동 실행**: Actions 탭 → Run workflow로 언제든 즉시 실행 가능합니다.
- **로그 확인**: Actions 탭에서 각 실행 결과와 오류 메시지를 확인할 수 있습니다.
- **무료 한도**: GitHub 무료 계정 기준 월 2,000분 제공. 이 자동화는 월 약 300분 사용합니다.
