from __future__ import annotations

import json
from typing import Any


def parse_leaf(raw: bytes) -> Any:
    if not raw:
        return None
    c = raw[0]
    if c == 0x22:  # '"'
        return json.loads(raw)
    if c == 0x74:  # 't'rue
        return True
    if c == 0x66:  # 'f'alse
        return False
    if c == 0x6E:  # 'n'ull
        return None
    # number: '-' or digit
    s = raw.decode("ascii")
    return float(s) if (b"." in raw or b"e" in raw or b"E" in raw) else int(s)


def parse_full(raw: bytes) -> Any:
    return json.loads(raw)
