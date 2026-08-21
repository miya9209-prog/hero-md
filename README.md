# MISHARP HERO ITEM OS

미샵의 신상품/주력상품을 **상품 마스터 → 조회/장바구니/판매 → 실제 재고 → 48H HERO 판정 → MD 실행**으로 연결하는 운영 OS입니다.

## 핵심 원칙

- **실제 재고의 기준은 Sellmate API**입니다. Cafe24 Admin의 재고수량은 HERO 판정과 재고 의사결정에 사용하지 않습니다.
- **상품 행동·판매 통계의 1차 기준은 Cafe24 Analytics**입니다.
  - 상품 조회: `/products/view`
  - 장바구니: `/carts/action`
  - 판매건수·판매수량·매출: `/products/sales`
- **SERA는 보완·교차검증 데이터**로 사용합니다.
  - 조회수, 주문, 수량, 매출, OpV, ESpV, 클릭가치
- Cafe24 상품 마스터는 `product_no`를 중심으로 연결하고, Sellmate는 `product_code/variant_code` 매핑을 지원합니다.

## 화면 구조

좌측 메뉴를 사용하지 않고 Streamlit `st.navigation(position="top")` 기반 상단 메뉴를 사용합니다.

`히로 레이더 | 상품 마스터 | 상품 스케줄 | 48H 판정 | 월간 HERO | MD 실행 | 데이터·설정`

이는 향후 SELLER OS의 한 모듈로 삽입하기 위한 구조입니다.

## 데이터 소스별 역할

| 데이터 | 기준 소스 | 역할 |
|---|---|---|
| 상품번호/상품명/가격 | Cafe24 Admin | 상품 마스터 |
| 상품 조회수 | Cafe24 Analytics | HERO 수요 신호 |
| 장바구니 담긴수/담김율 | Cafe24 Analytics | 구매의향 신호 |
| 판매건수/판매수량/매출 | Cafe24 Analytics | 전환/매출 신호 |
| 클릭가치/OpV/ESpV | SERA | 보완·교차검증 |
| 실제 재고 | **Sellmate API** | 재발주/결품/재고위험 판단 |
| Cafe24 Admin 재고 | 사용 안 함 | 참고도 하지 않는 것을 원칙으로 함 |

## 처음 실행

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
pip install -r requirements.txt
python -m scripts.init_db
streamlit run app.py
```

## 현재 기존 배포에서 바꿔야 하는 Secrets

기존 Cafe24 설정에 아래 scope를 포함시킨 뒤 **Cafe24 OAuth를 한 번 다시 승인**해야 Analytics가 동작합니다.

```toml
CAFE24_SCOPES = "mall.read_product mall.read_order mall.read_analytics"
```

Sellmate는 셀메이트 개발자 포털/신청을 통해 발급받은 **실제 API Base URL, Token, 재고 Endpoint, 응답 필드명**을 Secrets에 넣습니다. 공개 웹 정보만으로 고객별 API 스펙을 추정하지 않습니다.

자세한 과정은 `SETUP_GUIDE_KO.md`와 `docs/`를 보세요.
