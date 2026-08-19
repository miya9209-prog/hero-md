# 미샵 히로상품 예측·관리 시스템

> **처음 시작할 때는 [`00_먼저읽기.md`](00_먼저읽기.md)부터 보세요.**

미샵 MD팀의 기존 엑셀 업무를 **GitHub + Streamlit + Cafe24 API + Cafe24 Analytics + SERA + PostgreSQL** 구조로 전환하기 위한 실행 가능한 MVP 레포입니다.

## 이 프로그램이 하는 일

1. 신상품 소싱/노출 일정을 관리합니다.
2. 출시 전 히로 예상점수(HERO Score)를 계산합니다.
3. Cafe24 상품번호(product_no)를 중심키로 상품을 연결합니다.
4. Cafe24 Analytics의 상품조회·판매건수·판매수량·매출을 가져옵니다.
5. 상품 노출 후 정확한 48시간 실적을 계산합니다.
6. 조회·전환·조회당 매출(RPV)을 이용해 히로/숨은 히로/전환문제/저반응을 판정합니다.
7. SERA 엑셀 보고서를 보조 데이터로 적재합니다.
8. MD·제작팀 조치(Action)를 한 화면에서 관리합니다.
9. 월간 히로 목록과 매출순위·이익순위를 별도로 관리합니다.
10. GitHub Actions로 정기 수집을 자동화할 수 있습니다.

## 가장 쉬운 시작 순서

### 1) ZIP을 풀고 폴더로 이동

```bash
cd misharp-hero-md
```

### 2) 가상환경 만들기

Windows PowerShell:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3) DB 생성

처음에는 아무 설정 없이 SQLite로 실행됩니다.

```bash
python -m scripts.init_db
```

### 4) 기존 MD 엑셀 가져오기

```bash
python -m scripts.import_md_excel "미샵_핵심업무_실행서식3.xlsx"
```

### 5) 앱 실행

```bash
streamlit run app.py
```

브라우저에서 로컬 주소가 열리면 먼저 **설정·연동** 화면을 확인하세요.

---

## 운영 전환 순서

1. GitHub 저장소 생성
2. Supabase(PostgreSQL) 생성
3. Streamlit Community Cloud 1차 배포
4. 생성된 Streamlit 주소를 Cafe24 Redirect URI로 등록
5. Cafe24 Admin API 앱 등록
6. Cafe24 Analytics 권한 설정
7. Streamlit Secrets 입력
8. 앱에서 Cafe24 최초 인증
9. SERA 보고서 1~2개 시험 적재
10. GitHub Actions Secrets 입력
11. 자동수집 실행
12. 7~14일 기존 엑셀과 병행 검증

자세한 제작 과정은 **[SETUP_GUIDE_KO.md](SETUP_GUIDE_KO.md)** 를 위에서부터 그대로 따라가면 됩니다.

## 화면 용어 원칙

화면과 표는 한글을 우선합니다. 길이가 길어지는 경우 업계 표준 약어를 사용합니다.

- 구매전환율(CVR)
- 광고효율(ROAS)
- 객단가(AOV)
- 클릭률(CTR)
- 조회당 매출(RPV)
- 히로 점수(HERO Score)

## 중요

- 운영 DB에는 SQLite를 쓰지 마세요. Streamlit과 GitHub Actions가 서로 다른 서버에서 실행되므로 Supabase/Neon/RDS 같은 원격 PostgreSQL이 필요합니다.
- `.env`, `.streamlit/secrets.toml`, API 키, 토큰은 GitHub에 올리지 않습니다.
- SERA는 교차검증/보조원천으로 사용하고, 공식 자동수집의 기준은 Cafe24 Analytics API로 둡니다.
- 현재 엑셀에서 공급사상품명을 연결키로 사용하던 방식은 가져오기 호환용으로만 남기고, 프로그램 내부에서는 `product_no`와 내부 ID를 사용합니다.
