import argparse
from misharp_hero.db import init_db
from misharp_hero.services.md_excel_import import import_md_excel

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("file")
    args = p.parse_args()
    init_db()
    print(import_md_excel(args.file))
