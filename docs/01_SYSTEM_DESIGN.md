# 시스템 설계

## 데이터 흐름

```text
Cafe24 Admin
  └─ 상품 마스터(product_no, product_code, 상품명, 가격)

Cafe24 Analytics
  ├─ /products/view      → 조회수
  ├─ /carts/action       → 장바구니 담긴수/담김율
  └─ /products/sales     → 판매건수/판매수량/매출

SERA
  └─ 조회/주문/매출 + OpV/ESpV/클릭가치 보완

Sellmate API
  └─ 실제 재고(stock/available) = 재고 Source of Truth

       ↓ product_no / product_code 매핑

HERO Signal Layer
  ├─ CVR = 판매건수 / 조회수
  ├─ 장바구니율 = 담긴수 / 조회수
  ├─ RPV = 매출 / 조회수
  ├─ SERA 클릭가치/OpV/ESpV
  └─ Sellmate 현재고

       ↓

48H HERO Score / 자동진단 / MD 실행
```

## 왜 Cafe24 재고를 배제하는가

미샵의 실물 재고 운영 기준이 Sellmate이므로 Cafe24 Admin의 `stock_quantity`를 HERO ITEM OS 재고값으로 쓰면 불일치가 발생합니다. 따라서 Cafe24 상품 동기화 코드는 재고를 `products.stock_qty`에 갱신하지 않습니다.
