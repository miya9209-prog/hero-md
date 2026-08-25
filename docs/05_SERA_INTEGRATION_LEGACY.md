# SERA 연동

SERA는 Cafe24 Analytics의 대체가 아니라 **보완·교차검증 데이터**입니다.

사용 항목:
- 조회수
- 주문수
- 판매수량
- 매출
- OpV
- ESpV
- 클릭가치

## 입력 방법

기본: `데이터·설정 > SERA 엑셀 업로드`

신형 보고서는 상품번호/상품코드 컬럼을 직접 읽고, 구형 보고서는 상품상세경로 URL에서 `product_no`를 추출합니다.

## 선택적 자동화

SERA 보고서를 인증된 직접 다운로드 URL로 받을 수 있는 경우:

```text
SERA_REPORT_URL
SERA_AUTH_HEADER
SERA_AUTH_TOKEN
```

를 설정하면 `scripts.sync_sera_remote`로 자동 수집할 수 있습니다.
