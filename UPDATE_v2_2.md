# v2.2 적용 방법

현재 운영 레포 `miya9209-prog/hero-md` 기준입니다.

## 교체 방법
이 압축파일의 내용을 기존 GitHub 레포에 덮어쓴 뒤 Commit / Push 합니다.

주요 변경 파일:
- `misharp_hero/models.py`
- `misharp_hero/db.py`
- `misharp_hero/repository.py`
- `misharp_hero/ui.py`
- `misharp_hero/hero_score.py`
- `misharp_hero/services/cafe24_admin.py`
- `misharp_hero/services/sync.py`

## 배포 후 확인 순서
1. Streamlit이 정상 재부팅되는지 확인
2. 상단 `상품 마스터` 진입
3. 전체 상품 수가 기존과 동일한지 확인
4. 상품 하나 검색
5. `HERO 관찰 ON`, 출시일·시각, 시즌, 제작/사입을 입력하고 저장
6. `히로 레이더`에서 해당 상품이 관찰대상으로 나타나는지 확인
7. `48H 판정`에서 마감시각이 출시시각 + 48시간인지 확인

## 중요
기존 18,047개는 삭제하거나 재이관하지 않습니다.

v2.1에서 이미 동기화한 상품에는 새로 추가한 `판매상태/진열상태/소비자가/Cafe24 등록·수정시각`이 비어 있을 수 있습니다.
이 부가정보까지 모두 채우려면 배포 후 `데이터·설정 → Cafe24 상품 전체`를 **한 번만** 다시 실행합니다.
상품 저장은 Bulk Upsert이므로 `product_no` 기준으로 기존 행을 갱신하며, `product_md`의 MD 입력정보는 건드리지 않습니다.

## HERO 관찰 규칙
- OFF: 상품 마스터에만 존재, 자동 48H 수집 제외
- ON + 출시 전: 히로 레이더 대기
- ON + 출시 후 0~48H: 관찰중
- ON + 48H 경과: 48H 완료

HERO Score:
`CVR 30 + RPV 25 + 판매수량 20 + 매출 15 + 조회 10`
