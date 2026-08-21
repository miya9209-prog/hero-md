# Security

- Client Secret, Supabase DB password, Sellmate API Token, OAuth code를 GitHub에 커밋하지 않습니다.
- Streamlit Secrets / GitHub Actions Secrets만 사용합니다.
- OAuth access/refresh token은 `TOKEN_ENCRYPTION_KEY`로 암호화해 DB에 저장합니다.
- 오류 화면에 Secret 전체를 출력하지 않습니다.
- 사용자가 스크린샷을 공유할 때 Secret/API Token/DB URL을 가립니다.
