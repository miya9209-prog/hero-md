import argparse
from misharp_hero.db import init_db
from misharp_hero.services.sera_import import import_sera_excel

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("file")
    args = p.parse_args()
    init_db()
    count = import_sera_excel(args.file)
    print(f"SERA {count}행 적재 완료")
