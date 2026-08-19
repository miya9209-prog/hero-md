# 보안 운영 규칙

1. Client Secret, Access Token, Refresh Token, DB 비밀번호를 GitHub 코드에 직접 쓰지 않습니다.
2. `.env`와 `.streamlit/secrets.toml`은 커밋하지 않습니다.
3. 운영 DB는 외부에 공개하지 않습니다.
4. TOKEN_ENCRYPTION_KEY는 별도 안전한 장소에도 백업합니다.
5. GitHub Actions와 Streamlit의 Secret은 필요 최소권한으로 운영합니다.
6. Cafe24 앱 권한은 읽기권한 중심으로 시작합니다.
7. 토큰/비밀번호가 노출된 경우 즉시 폐기·재발급합니다.
