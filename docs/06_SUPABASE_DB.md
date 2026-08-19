# Supabase PostgreSQL

공식 참고:

https://supabase.com/docs/guides/database/overview

## 운영에서 필요한 이유

Streamlit 서버와 GitHub Actions runner가 DB를 함께 사용해야 합니다.

## 연결

Supabase Dashboard → Connect

Session pooler 문자열을 복사합니다.

SQLAlchemy 형식:

```text
postgresql+psycopg://USER:PASSWORD@HOST:5432/postgres
```

Secret:

```text
DATABASE_URL=...
```

그 다음:

```bash
python -m scripts.init_db
```
