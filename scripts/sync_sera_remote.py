from misharp_hero.db import init_db
from misharp_hero.services.sera_remote import sync_sera_remote

if __name__ == "__main__":
    init_db()
    print(sync_sera_remote())
