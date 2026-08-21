# Sellmate API 연동 — 실제 재고 기준

## 원칙

**HERO ITEM OS의 재고 Source of Truth는 Sellmate입니다.**
Cafe24 Admin 재고는 사용하지 않습니다.

## 왜 설정형 Adapter인가

셀메이트는 공식 Developer Portal과 API 신청 안내를 운영하지만, 고객별로 발급받는 API의 실제 Endpoint/인증/응답 필드 스펙은 발급 문서를 확인해야 합니다. 따라서 이 레포는 임의 엔드포인트를 추정하지 않고 Secrets로 주입합니다.

## 필요한 값

셀메이트에서 API 발급 후 아래를 확인합니다.
- API Base URL
- 인증 Token/API Key
- 재고 조회 Endpoint
- HTTP Method(GET/POST)
- 페이지 방식(page/offset/없음)
- 응답 목록 위치 예: `data`, `result.items`
- 상품번호/상품코드/품목코드/재고/가용재고 필드명

## Secrets 예

```toml
SELLMATE_ENABLED = "true"
SELLMATE_API_BASE_URL = "발급문서의 Base URL"
SELLMATE_API_TOKEN = "발급키"
SELLMATE_INVENTORY_PATH = "발급문서의 재고 Endpoint"
SELLMATE_INVENTORY_METHOD = "GET"
SELLMATE_AUTH_HEADER = "Authorization"
SELLMATE_AUTH_PREFIX = "Bearer"
SELLMATE_PAGE_MODE = "page"
SELLMATE_PAGE_PARAM = "page"
SELLMATE_PAGE_SIZE_PARAM = "limit"
SELLMATE_PAGE_SIZE = "100"
SELLMATE_RESPONSE_LIST_KEY = "data"
SELLMATE_PRODUCT_NO_FIELD = "product_no"
SELLMATE_PRODUCT_CODE_FIELD = "product_code"
SELLMATE_VARIANT_CODE_FIELD = "variant_code"
SELLMATE_STOCK_FIELD = "stock_qty"
SELLMATE_AVAILABLE_FIELD = "available_qty"
SELLMATE_WAREHOUSE_FIELD = "warehouse"
```

필드명이 다르면 Secrets만 바꾸면 됩니다.

## 매핑

1. Sellmate 응답에 Cafe24 `product_no`가 있으면 직접 연결
2. 없으면 Sellmate `product_code` ↔ Cafe24 `products.product_code` 연결
3. 품목 재고는 상품번호별로 합산하여 상품 마스터/48H 판정에 표시
