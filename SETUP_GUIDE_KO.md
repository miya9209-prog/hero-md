# MISHARP HERO ITEM OS 설치·연동 가이드

## A. 이미 만들어 둔 Streamlit/Supabase를 그대로 쓰는 경우

기존 `DATABASE_URL`, `TOKEN_ENCRYPTION_KEY`, Cafe24 Client ID/Secret은 그대로 사용할 수 있습니다.
새 코드가 추가 테이블을 `create_all()`로 생성하므로 기존 상품 18,047개와 OAuth 토큰을 지우지 않습니다.

### 1) Cafe24 Scope 수정

Streamlit Secrets와 GitHub Actions Secrets의 `CAFE24_SCOPES`를 아래로 바꿉니다.

```text
mall.read_product mall.read_order mall.read_analytics
```

그 다음 앱의 `데이터·설정`에서 Cafe24 권한승인을 **다시 한 번** 하고 새 code로 토큰 저장을 합니다.

### 2) Analytics 테스트

`데이터·설정 > Cafe24 Analytics 테스트`

정상이라면 최근 24시간 상품조회 지표 건수가 표시됩니다.

### 3) Sellmate

셀메이트 API는 발급받은 고객별 문서를 기준으로 설정합니다. `docs/04_SELLMATE_API.md` 참고.

### 4) SERA

`데이터·설정 > SERA 데이터`에서 최신 엑셀을 업로드합니다.

### 5) 자동화

GitHub Actions에 동일한 Secrets를 등록합니다.
- 30분: Analytics 최근 2일 재집계 + Sellmate 현재고 + 48H HERO
- 매일 KST 03:13: Cafe24 상품 전체 재검증 + Analytics + Sellmate

## B. 데이터 우선순위

- 조회/장바구니/판매: Cafe24 Analytics 우선
- Analytics 값이 아직 없을 경우 SERA 값으로 임시 보완
- OpV/ESpV/클릭가치: SERA
- 재고: Sellmate만 사용

## C. 기존 DB 데이터 보존

이번 버전은 기존 `products`, `oauth_tokens`, `launches`, `metrics_48h`를 유지합니다.
신규 테이블만 추가합니다.
- `analytics_product_metrics`
- `inventory_current`
- `hero_metrics_v2`
