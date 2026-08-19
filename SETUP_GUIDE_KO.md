# 미샵 히로상품 예측·관리 시스템 — 처음부터 끝까지 설치 가이드

이 문서는 개발 경험이 많지 않아도 그대로 따라갈 수 있도록 작성했습니다.

---

# 0. 전체 구조 먼저 이해하기

```text
[MD 입력]
공급사상품명 / 공급가 / FOCUS / HERO DNA / 발주 / 메모
        │
        ▼
[미샵 히로 DB] ◀──────── [SERA 엑셀]
        ▲
        │
 ┌──────┴──────────────┐
 │                     │
[Cafe24 Admin API]  [Cafe24 Analytics]
상품/가격/주문/재고    조회/판매/매출
 │                     │
 └──────────┬──────────┘
            ▼
     [히로 점수/진단]
            ▼
       [Streamlit]
 MD팀 / 제작팀 / 대표 공유
            ▲
            │
     [GitHub Actions]
      정기 자동수집
```

핵심 원칙은 **상품명으로 연결하지 않는 것**입니다.

프로그램 내부 연결 우선순위:

1. Cafe24 상품번호(product_no)
2. 내부 상품 ID
3. 상품코드(product_code)
4. 기존 엑셀 이관 시에만 상품명 보조매칭

---

# 1. PC 준비

필수:

- Python 3.11~3.13 권장
- Git 또는 GitHub Desktop
- GitHub 계정
- Streamlit Community Cloud 계정
- Cafe24 Developers 계정
- 운영 시 PostgreSQL DB

압축을 풀고 터미널에서:

```bash
cd misharp-hero-md
```

가상환경:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

정상 확인:

```bash
python -m scripts.doctor
```

---

# 2. 가장 먼저 로컬에서 실행

아직 Cafe24 키가 없어도 됩니다.

```bash
python -m scripts.init_db
streamlit run app.py
```

기본 DB:

```text
sqlite:///misharp_hero.db
```

이 단계에서는 화면 구조와 MD 엑셀 이관을 확인합니다.

---

# 3. 기존 MD 엑셀 이관

현재 기준 파일:

```text
미샵_핵심업무_실행서식3.xlsx
```

레포 폴더에 복사한 다음:

```bash
python -m scripts.import_md_excel "미샵_핵심업무_실행서식3.xlsx"
```

이 importer는 다음 시트를 읽습니다.

- 1.상품스케줄표
- 2.주간상품체크(제작팀공유)
- 3.월별HERO LIST
- 4.MD주간회의록
- 5.MD월간회의록

### 기존 엑셀에서 프로그램으로 바뀌는 핵심

기존:
`공급사상품명 → 노출상품명 → MATCH`

변경:
`내부 ID → product_no → 상품명`

또한 기존 3번 시트에서 `월내 매출 순위`가 공헌이익률(H열)을 기준으로 계산되는 수식 오류가 있으므로 프로그램에서는 다음을 분리합니다.

- 매출순위
- 공헌이익률 순위
- 공헌이익액 순위

---

# 4. GitHub 저장소 만들기

## 방법 A — GitHub Desktop 권장

1. GitHub Desktop 설치
2. File → Add local repository
3. 이 `misharp-hero-md` 폴더 선택
4. "create a repository" 선택
5. Repository name: `misharp-hero-md`
6. Publish repository
7. 회사 내부용이면 **Private** 권장

## 방법 B — 명령어

GitHub에서 빈 저장소를 먼저 만든 뒤:

```bash
git init
git add .
git commit -m "미샵 히로 MD 시스템 초기 버전"
git branch -M main
git remote add origin <내 GitHub 저장소 주소>
git push -u origin main
```

절대 올리면 안 되는 파일은 `.gitignore`에 이미 포함되어 있습니다.

---

# 5. 운영 DB 만들기 — Supabase 권장

왜 필요한가?

Streamlit과 GitHub Actions는 서로 다른 컴퓨터에서 실행됩니다.
로컬 SQLite 파일은 서로 공유되지 않습니다.

따라서 운영은 PostgreSQL을 사용합니다.

Supabase에서:

1. 새 프로젝트 생성
2. DB 비밀번호를 안전하게 보관
3. Dashboard → Connect
4. **Session pooler** 연결문자열 복사 권장
5. SQLAlchemy용으로 앞부분을 아래처럼 사용

```text
postgresql+psycopg://USER:PASSWORD@HOST:5432/postgres
```

`.env` 또는 Streamlit Secrets:

```text
DATABASE_URL=postgresql+psycopg://...
```

그 다음:

```bash
python -m scripts.init_db
```

---

# 6. Streamlit을 먼저 1차 배포

Cafe24 앱 등록에는 Redirect URI가 필요하므로 Streamlit 주소를 먼저 확보하면 쉽습니다.

1. Streamlit Community Cloud 접속
2. Create app
3. GitHub 저장소 선택
4. Branch: `main`
5. Main file: `app.py`
6. Deploy
7. 생성된 주소 기록

예:

```text
https://misharp-hero-md.streamlit.app/
```

첫 배포에서 DB/API 경고가 나와도 괜찮습니다.
이 단계 목적은 **고정 Redirect URI 확보**입니다.

---

# 7. Cafe24 Admin API 연결

Cafe24 Developers에서 앱을 생성합니다.

Admin 앱의 최소 읽기권한은 다음을 사용합니다.

```text
mall.read_product
mall.read_order
```

**Cafe24 Analytics는 별도의 Analytics 앱을 생성해 OAuth 인증합니다.** `mall.read_analytics`는 아래 8단계 Analytics 앱에서 사용합니다.

설정값:

```text
CAFE24_MALL_ID=내 몰아이디
CAFE24_CLIENT_ID=...
CAFE24_CLIENT_SECRET=...
CAFE24_REDIRECT_URI=https://내앱.streamlit.app/
CAFE24_SCOPES=mall.read_product mall.read_order
CAFE24_API_VERSION=2026-03-01
```

앱을 실행한 뒤:

**설정·연동 → Cafe24 Admin 인증 링크 만들기**

버튼을 누르면 승인 URL이 생성됩니다.

1. 승인 URL 열기
2. 쇼핑몰 관리자 로그인
3. 권한 승인
4. Streamlit 주소로 돌아오며 URL에 `code=`가 붙습니다.
5. 화면의 `code` 입력란에 붙여넣기
6. 토큰 저장

Access Token은 짧은 시간만 유효하므로 프로그램은 Refresh Token으로 자동 갱신하도록 구성되어 있습니다.

### 토큰 보안

토큰은 DB에 암호화 저장합니다.

암호화 키 만들기:

```bash
python -m scripts.generate_fernet_key
```

출력값:

```text
TOKEN_ENCRYPTION_KEY=...
```

운영 시작 후 이 키를 잃어버리면 저장된 토큰을 복호화할 수 없습니다.

---

# 8. Cafe24 Analytics 연결

이 시스템에서 48시간 히로 판정의 핵심입니다.

사용 API:

```text
GET /products/view
GET /products/sales
```

가져오는 주요 값:

- 상품번호
- 상품명
- 상품조회수
- 판매건수
- 판매수량
- 매출액

프로그램 계산:

```text
구매전환율(CVR) = 판매건수 ÷ 상품조회수
수량전환율 = 판매수량 ÷ 상품조회수
조회당 매출(RPV) = 매출액 ÷ 상품조회수
```

Cafe24 공식 Analytics 문서의 권한:

```text
mall.read_analytics
```

### Analytics 앱 생성

Cafe24 Developers의
`Data → Cafe24 Analytics API → Creating Cafe24 Analytics App`
절차에 따라 **Analytics 전용 앱을 별도로 만듭니다.**

아래 Secret을 사용합니다.

```text
CAFE24_ANALYTICS_CLIENT_ID=...
CAFE24_ANALYTICS_CLIENT_SECRET=...
CAFE24_ANALYTICS_REDIRECT_URI=https://내앱.streamlit.app/
# 아래 URL 2개는 보통 비워도 됩니다. 프로그램이 mall_id로 공식 OAuth URL을 만듭니다.
CAFE24_ANALYTICS_AUTHORIZE_URL=
CAFE24_ANALYTICS_TOKEN_URL=
```

Analytics 인증코드/토큰 endpoint는 Admin OAuth와 같은 `https://{mall_id}.cafe24api.com/api/v2/oauth/...` 형식이지만, **Analytics 앱에서 발급받은 별도 Client ID/Secret과 토큰을 사용**합니다.

---

# 9. SERA 데이터 연결

SERA는 두 방식으로 사용합니다.

## 1순위 — Cafe24 Analytics API 자동수집

운영의 기준 원천입니다.

## 2순위 — SERA 엑셀 교차검증

SERA에서 엑셀 보고서를 내려받은 뒤:

```bash
python -m scripts.import_sera_report "SERA_report_20260818_163023.xlsx"
```

또는 Streamlit의 **데이터 가져오기** 화면에서 파일을 업로드합니다.

parser는 다음 이름을 자동 탐색합니다.

```text
상품번호
상품코드
상품명
상품상세경로
조회수
주문수
판매수량
매출액
OpV
ESpV
클릭가치
```

구형 보고서에 상품번호가 없으면 `상품상세경로` URL의 `product_no`를 추출합니다.

SERA 표의 열 이름이 달라져도 `misharp_hero/services/sera_import.py`의 `ALIASES`만 추가하면 됩니다.

---

# 10. Streamlit Secrets 입력

Streamlit 앱:

Settings → Secrets

예:

```toml
DATABASE_URL = "postgresql+psycopg://..."
TOKEN_ENCRYPTION_KEY = "..."

CAFE24_MALL_ID = "..."
CAFE24_CLIENT_ID = "..."
CAFE24_CLIENT_SECRET = "..."
CAFE24_REDIRECT_URI = "https://내앱.streamlit.app/"
CAFE24_SCOPES = "mall.read_product mall.read_order"
CAFE24_API_VERSION = "2026-03-01"

# Analytics 별도 앱일 때만
CAFE24_ANALYTICS_CLIENT_ID = ""
CAFE24_ANALYTICS_CLIENT_SECRET = ""
CAFE24_ANALYTICS_REDIRECT_URI = ""
CAFE24_ANALYTICS_AUTHORIZE_URL = ""
CAFE24_ANALYTICS_TOKEN_URL = ""
```

`secrets.toml`은 GitHub에 절대 올리지 않습니다.

---

# 11. 최초 Cafe24 동기화

설정이 끝나면:

```bash
python -m scripts.sync_cafe24 --products
```

현재 관찰중인 상품의 48시간 실적 갱신:

```bash
python -m scripts.sync_cafe24 --launches
```

전체:

```bash
python -m scripts.sync_cafe24 --products --launches
```

---

# 12. GitHub Actions 자동수집

GitHub 저장소:

Settings → Secrets and variables → Actions → New repository secret

최소:

```text
DATABASE_URL
TOKEN_ENCRYPTION_KEY
CAFE24_MALL_ID
CAFE24_CLIENT_ID
CAFE24_CLIENT_SECRET
CAFE24_REDIRECT_URI
CAFE24_SCOPES
CAFE24_API_VERSION
```

Analytics 별도 앱이면 추가:

```text
CAFE24_ANALYTICS_CLIENT_ID
CAFE24_ANALYTICS_CLIENT_SECRET
CAFE24_ANALYTICS_REDIRECT_URI
CAFE24_ANALYTICS_AUTHORIZE_URL
CAFE24_ANALYTICS_TOKEN_URL
```

포함된 workflow:

```text
.github/workflows/sync_30min.yml
.github/workflows/sync_daily.yml
```

- 매시 17분/47분: 관찰중 상품 갱신
- 매일 **한국시간 03:13**: 상품마스터 재동기화 + 관찰상품 재검증

GitHub Actions의 cron은 기본 UTC이므로 일일 workflow는 `18:13 UTC`로 넣어 한국시간 03:13에 실행되게 했습니다. 정각을 피한 이유는 GitHub 예약실행이 정각 부근 부하로 지연될 수 있기 때문입니다.

---

# 13. 히로 점수(HERO Score)

## 출시 전

현재 MVP 가중치:

```text
MD 평가            25
과거 HERO DNA      20
공헌이익률          15
시즌 적합도         15
재주문 가능성       10
콘텐츠 확장성       10
FOCUS 후보           5
```

데이터가 누적되면 거래처 성공률, 카테고리 성공률, 가격대 성공률을 자동학습 항목으로 추가합니다.

## 출시 후 48시간

데이터가 5개 이상 누적되면 같은 히스토리 내 백분위로 평가합니다.

```text
구매전환율(CVR)     30
조회당 매출(RPV)    25
판매수량            20
매출액              15
조회수              10
```

판정:

```text
85~100  🔥 HERO
70~84   💎 HERO 유력
55~69   관찰
0~54    재검토
```

진단 매트릭스:

```text
조회 높음 + 전환 높음 = HERO
조회 낮음 + 전환 높음 = 숨은 HERO → 노출 확대
조회 높음 + 전환 낮음 = 전환 문제 → 썸네일/상세/가격/핏 점검
조회 낮음 + 전환 낮음 = 저반응 → 우선순위 축소
```

---

# 14. 48시간은 정확한 시간으로 관리

기존 엑셀:

```text
노출날짜 + 2일
```

프로그램:

```text
launch_at + 48시간
```

예:

```text
8/19 16:20 노출
→ 8/21 16:20 마감
```

Analytics API의 `start_datetime`, `end_datetime`을 사용하도록 설계했습니다.

---

# 15. 운영 첫 2주는 반드시 병행검증

엑셀과 프로그램을 같이 봅니다.

검증:

- 상품조회수
- 판매건수
- 판매수량
- 매출액
- CVR
- RPV
- 48시간 시작/종료시각
- product_no 매칭
- SERA와 Analytics 차이

차이가 있으면 UI부터 바꾸지 말고 **데이터 정의와 connector**를 먼저 확인합니다.

---

# 16. 추천 운영 루틴

### 매일 오전

`오늘의 히로 레이더`

- 48H 마감 임박
- HERO 유력
- 숨은 HERO
- 전환문제
- 재고위험
- 미완료 Action

### 신상품 노출 직전

`상품 스케줄`

- FOCUS 여부
- HERO DNA
- MD 평가
- 시즌 적합도
- 초도량
- 예상 HERO Score

### 매주 금요일

`MD Action·주간회의`

- HERO 확대
- 숨은 HERO 노출 확대
- 저전환 보완
- 재검토 종료/유지
- 제작팀 Action

### 월말

`월간 HERO`

- 확정 HERO
- 매출순위
- 이익순위
- 재주문 성공
- FOCUS 적중률
- 다음달 DNA 후보
