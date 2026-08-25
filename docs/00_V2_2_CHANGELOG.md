# MISHARP HERO ITEM OS v2.2 변경사항

## 이번 버전의 목적
Cafe24 전체 상품 동기화 이후, 상품 마스터를 단순 조회표가 아니라 **MD 운영의 기준 데이터**로 전환합니다.

## 1. Cafe24 원본과 MD 운영정보 분리
새 테이블 `product_md`를 추가했습니다.

Cafe24가 갱신하는 값:
- 상품번호 `product_no`
- 상품코드
- 상품명
- 판매가 / 소비자가
- 판매상태 / 진열상태
- Cafe24 등록·수정시각
- 이미지 등

MD가 HERO ITEM OS에서 관리하는 값:
- HERO 관찰 ON/OFF
- 출시일시 `launch_at`
- 판매종료일
- 시즌
- 미샵제작 / 사입
- MD 담당
- MD 메모

Cafe24 상품을 다시 동기화해도 `product_md` 값은 덮어쓰지 않습니다.

## 2. 상품 마스터 페이지네이션
18,000개 이상의 상품을 한 번에 읽지 않습니다.

- 검색: 상품명 / 상품코드 / 상품번호
- 필터: 판매상태 / 진열상태 / HERO 관찰 / 카테고리 / 시즌 / 제작·사입
- 표시수: 50 / 100 / 200
- 이전 / 다음 페이지
- 기간 성과는 현재 페이지의 상품번호만 조회

## 3. HERO 관찰 자동 연결
상품 마스터에서:

`HERO 관찰 ON + 출시일시 저장`

하면 해당 상품의 `launches` 행을 자동 생성 또는 갱신합니다.

- 시작: `launch_at`
- 종료: `launch_at + 48시간`
- product_no 기준 연결
- HERO 관찰 OFF 시 히로 레이더와 48H 자동수집 대상에서 제외

## 4. 상품 마스터 화면 구조
### 운영 마스터
- 상품번호
- 상품코드
- 상품명
- 판매가 / 소비자가
- 판매상태 / 진열상태
- 카테고리
- 제작/사입
- 시즌
- HERO 관찰
- 출시시각
- 48H 상태
- HERO Score / 등급
- Sellmate 재고
- MD 담당

### 기간 성과
- 조회수
- 장바구니
- 장바구니율
- 판매건수
- 판매수량
- 매출
- CVR
- RPV
- SERA 보완지표

## 5. HERO Score 가중치 수정
확정 기준으로 통일했습니다.

- CVR 30
- RPV 25
- 판매수량 20
- 매출액 15
- 조회수 10

장바구니율과 SERA 클릭가치는 HERO Score에서 제외하고 진단 보조지표로만 사용합니다.

## 6. 기존 DB 자동 마이그레이션
앱 시작 시 기존 `products` 테이블에 필요한 Cafe24 부가 컬럼이 없으면 자동 추가합니다.

추가 컬럼:
- retail_price
- display
- selling
- cafe24_created_at
- cafe24_updated_at

새 `product_md` 테이블도 자동 생성됩니다.

Supabase SQL Editor에서 수동 SQL을 실행할 필요가 없습니다.

## 7. 기존 데이터 보존
- 기존 products 유지
- 기존 launches 유지
- 기존 48H 지표 유지
- OAuth 토큰 유지
- SERA / Analytics / Sellmate 데이터 유지

`product_no` 연결 원칙은 그대로 유지합니다.
