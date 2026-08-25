# MISHARP HERO ITEM OS v3.0 설치·운영 가이드

## 1. 필수 환경
- Python 3.11~3.13
- Streamlit Community Cloud
- Supabase PostgreSQL
- Cafe24 Admin OAuth
- GitHub Actions

## 2. Streamlit Secrets
```toml
DATABASE_URL = "postgresql+psycopg://..."
TOKEN_ENCRYPTION_KEY = "..."
CAFE24_MALL_ID = "miyawa"
CAFE24_CLIENT_ID = "..."
CAFE24_CLIENT_SECRET = "..."
CAFE24_REDIRECT_URI = "https://hero-md.streamlit.app/"
CAFE24_SCOPES = "mall.read_product mall.read_order mall.read_analytics"
CAFE24_API_VERSION = "2026-03-01"
CAFE24_SHOP_NO = "1"


MISHARP_HOME_URL = "https://misharp.co.kr/"
MISHARP_NEW_PRODUCT_URL = ""
NEW_PRODUCT_DISCOVERY_LOOKBACK_HOURS = "72"
HOME_CRAWL_MAX_AGE_DAYS = "14"
```

## 3. 팀 공용 메뉴
`상품DB`, `데이터·설정`, `미샵 DNA`는 별도 비밀번호 없이 팀에서 공용으로 사용합니다.

## 4. Cafe24
`데이터·설정 → Cafe24 OAuth`에서 한 번 승인합니다.
Access Token 만료 시 refresh token으로 자동갱신합니다.

## 5. 자동 신상품 탐색
공식 기준은 Cafe24 API입니다.
- 최근 등록
- 판매중
- 진열중

홈페이지 크롤링은 실제 노출 교차확인용입니다.
홈페이지 구조가 바뀌어 크롤링이 실패해도 Cafe24 API 자동탐색은 계속 동작합니다.

## 6. 30분 자동화
GitHub Actions:
`.github/workflows/sync_30min.yml`

매시 17분/47분:
1. 최근 상품DB 갱신
2. 신상품 자동탐색
3. 48시간 Analytics 갱신
4. 완료상품 반품률 갱신

## 7. 일일 자동화
`.github/workflows/sync_daily.yml`

KST 03:13:
- 상품DB 전체 재검증
- 최근 2일 Analytics
- 48시간 데이터
- 신상품 재탐색

## 8. 최근 3년 데이터
전체 20년 상품DB는 삭제하지 않습니다.
WHY/예측의 비교대상은 최근 3년을 우선합니다.

과거 Analytics backfill은 서버부하와 API 제한을 고려해
먼저 `데이터·설정 → 지난달 1개월 시험수집`으로 확인한 뒤
GitHub Actions의 `최근 3년 HERO 학습데이터 수집`을 수동 실행합니다.

## 9. 직원 사용
상단 `이용방법` 페이지가 공식 업무 매뉴얼입니다.
