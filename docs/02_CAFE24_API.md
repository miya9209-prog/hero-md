# Cafe24 연동

## 권한

권장 Scope:

```text
mall.read_product mall.read_order mall.read_analytics
```

Cafe24 Analytics 공식 문서에서는 접속통계 읽기권한이 `mall.read_analytics`이며, EC Admin API에서 발급한 접근 토큰을 Analytics API에도 사용할 수 있다고 안내합니다.

## 사용 API

### Admin
- 상품 목록: `/api/v2/admin/products`
- 전체상품이 5,000개를 넘는 경우 `since_product_no` 사용

### Analytics
- `https://ca-api.cafe24data.com/products/view`
- `https://ca-api.cafe24data.com/carts/action`
- `https://ca-api.cafe24data.com/products/sales`

각 Analytics 목록은 최대 1,000개 단위로 offset pagination합니다.
