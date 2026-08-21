from __future__ import annotations

import tempfile
from pathlib import Path

import requests

from misharp_hero.config import SERA_REPORT_URL, SERA_AUTH_HEADER, SERA_AUTH_TOKEN
from misharp_hero.services.sera_import import import_sera_excel


def sync_sera_remote():
    if not SERA_REPORT_URL:
        return 0
    headers = {}
    if SERA_AUTH_HEADER and SERA_AUTH_TOKEN:
        headers[SERA_AUTH_HEADER] = SERA_AUTH_TOKEN
    r = requests.get(SERA_REPORT_URL, headers=headers, timeout=120)
    r.raise_for_status()
    suffix = ".xlsx"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(r.content)
        path = tmp.name
    return import_sera_excel(path)
