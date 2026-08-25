# 데이터 우선순위

## 판매/조회/장바구니
1. Cafe24 Analytics
2. SERA 보완

## 클릭 관련
- Cafe24 Analytics의 상품 조회와 장바구니 행동을 사용
- SERA의 클릭가치/OpV/ESpV를 추가 신호로 사용

## 재고
1. Sellmate API만 사용
2. Cafe24 Admin stock_quantity는 미사용

## 불일치가 생기면
- 판매/매출: Analytics를 화면 공식값으로 두고 SERA 편차를 점검
- 재고: Sellmate를 무조건 공식값으로 둠
