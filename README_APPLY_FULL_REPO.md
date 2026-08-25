# MISHARP HERO ITEM OS v3.1 DNA 전체 레포 적용

## 최종 메뉴
1. 상품 탐색
2. 상품 판정 및 후속업무 관리
3. 미샵 DNA
4. 상품DB
5. 데이터·설정

별도 관리자 비밀번호는 사용하지 않습니다.

## 적용
1. 기존 GitHub `hero-md` 레포의 파일은 먼저 삭제하지 않습니다.
2. 이 ZIP 안의 **폴더 자체가 아니라 안쪽 내용 전체**를 레포 루트에 업로드해 같은 경로 파일을 덮어씁니다.
3. 기존 Streamlit Secrets와 GitHub Actions Repository secrets는 그대로 유지합니다.
4. Commit 후 Streamlit에서 Reboot app을 실행합니다.
5. 첫 화면, 상품 판정, 미샵 DNA, 상품DB, 데이터·설정 순서로 확인합니다.

## 미샵 DNA 전제
미샵 DNA는 `analytics_history_monthly` 최근 3년 학습데이터를 사용합니다. 데이터가 비어 있으면 `데이터·설정 → 최근 3년 비교데이터`에서 1개월 시험수집 후 GitHub Actions의 history backfill을 실행합니다.

## 보존
기존 Supabase 상품/토큰/HERO/반품/업무 데이터는 삭제하지 않습니다. DB migration은 필요한 테이블·컬럼만 추가합니다.
