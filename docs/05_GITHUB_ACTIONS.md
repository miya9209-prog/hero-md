# GitHub Actions

공식 참고:

https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows

## 현재 스케줄

30분:

```text
17,47 * * * *
```

일일(한국시간 03:13):

```text
13 18 * * *
```

GitHub Actions cron 기본 기준인 UTC 18:13은 한국시간(KST) 다음날 03:13입니다.

GitHub 공식 문서도 정각 부근은 예약 workflow 부하로 지연될 수 있음을 안내하므로 17분/47분을 사용합니다.

## 수동 실행

GitHub → Actions → workflow → Run workflow
