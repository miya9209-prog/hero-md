from misharp_hero.config import (
    DATABASE_URL, TOKEN_ENCRYPTION_KEY, CAFE24_MALL_ID, CAFE24_CLIENT_ID,
    CAFE24_CLIENT_SECRET, CAFE24_REDIRECT_URI, CAFE24_SCOPES
)
from misharp_hero.db import init_db, get_engine
from misharp_hero.services.sellmate import SellmateClient


def check(name, ok, detail=""):
    mark = "OK" if ok else "확인필요"
    print(f"[{mark}] {name} {detail}")


if __name__ == "__main__":
    try:
        init_db()
        with get_engine().connect() as c:
            c.exec_driver_sql("SELECT 1")
        db_ok = True
    except Exception as e:
        db_ok = False
        print("DB 오류:", e)

    check("DB 연결", db_ok, DATABASE_URL.split("@")[-1] if DATABASE_URL else "")
    check("TOKEN_ENCRYPTION_KEY", bool(TOKEN_ENCRYPTION_KEY))
    check("CAFE24_MALL_ID", bool(CAFE24_MALL_ID))
    check("CAFE24_CLIENT_ID", bool(CAFE24_CLIENT_ID))
    check("CAFE24_CLIENT_SECRET", bool(CAFE24_CLIENT_SECRET))
    check("CAFE24_REDIRECT_URI", bool(CAFE24_REDIRECT_URI), CAFE24_REDIRECT_URI)
    check("Cafe24 Analytics Scope", "mall.read_analytics" in CAFE24_SCOPES, CAFE24_SCOPES)
    check("Sellmate API", SellmateClient().configured(), "configured" if SellmateClient().configured() else "pending")
