from __future__ import annotations

from misharp_hero.db import init_db
from misharp_hero.repository import cleanup_legacy_discovery_active


def main():
    init_db()
    print("cleaned:", cleanup_legacy_discovery_active())


if __name__ == "__main__":
    main()
