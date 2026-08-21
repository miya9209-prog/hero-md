# Cafe24 Analytics 설계

## 제품별 핵심 지표

| 지표 | API | HERO ITEM OS 컬럼 |
|---|---|---|
| 상품조회수 | `/products/view` | views |
| 장바구니 담긴수 | `/carts/action` | cart_count |
| 장바구니 담김율 | `/carts/action` | cart_rate |
| 판매건수 | `/products/sales` | order_count |
| 판매물품수 | `/products/sales` | qty |
| 매출액 | `/products/sales` | revenue |

파생:
- CVR = order_count / views
- 수량전환율 = qty / views
- RPV = revenue / views

## 자동수집

`python -m scripts.sync_cafe24 --analytics --analytics-days 2`

당일은 계속 변하므로 30분 작업이 최근 2일을 덮어써서 지연집계/수정값을 반영합니다.
