from cryptography.fernet import Fernet
from misharp_hero.config import TOKEN_ENCRYPTION_KEY

def _fernet():
    if not TOKEN_ENCRYPTION_KEY:
        raise RuntimeError("TOKEN_ENCRYPTION_KEY가 없습니다. scripts.generate_fernet_key를 먼저 실행하세요.")
    return Fernet(TOKEN_ENCRYPTION_KEY.encode())

def encrypt_text(value: str | None):
    if not value:
        return None
    return _fernet().encrypt(value.encode()).decode()

def decrypt_text(value: str | None):
    if not value:
        return None
    return _fernet().decrypt(value.encode()).decode()
