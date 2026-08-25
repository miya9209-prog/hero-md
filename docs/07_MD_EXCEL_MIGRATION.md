# 기존 MD 엑셀 이관

명령:

```bash
python -m scripts.import_md_excel "미샵_핵심업무_실행서식3.xlsx"
```

## 주의

기존 2번 시트에는 판매건수와 판매수량이 분리되어 있지 않습니다.

따라서 최초 엑셀 이관에서는:

```text
판매건수 = 판매수량
```

을 임시값으로 넣습니다.

Cafe24 Analytics가 연결되면:

```text
판매건수 = order_count
판매수량 = order_product_count
```

으로 정확히 교체됩니다.

## 기존 월간 HERO 수식 보정

기존 J열 제목은 월내 매출순위지만 H열 공헌이익률을 RANK하는 수식이 들어 있습니다.

프로그램은 다음을 분리합니다.

```text
매출순위
공헌이익액 순위
공헌이익률 순위
```
