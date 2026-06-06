"""Parse the ``key: value`` text output of RouterOS print commands.

Most read commands emit aligned ``  some-key: some value   `` lines. When a
command streams progress (e.g. ``check-for-updates`` first prints "finding out
latest version..." and then the final block), the same key appears twice and
the LAST occurrence wins — which is what we want.
"""

from __future__ import annotations

import re

_KEY = re.compile(r"^\s*([\w-]+):\s*(.*?)\s*$")


def kv_dict(text: str) -> dict[str, str]:
    """Parse ``key: value`` lines into a dict. Later occurrences override earlier."""
    out: dict[str, str] = {}
    for line in (text or "").splitlines():
        m = _KEY.match(line)
        if m:
            out[m.group(1)] = m.group(2)
    return out


def is_unknown_command(text: str) -> bool:
    """Detect 'bad command name X' / 'no such item' / 'syntax error' replies.

    RouterOS returns these as ordinary stdout on the SSH channel, so callers
    need to recognise them before trying to parse a value list.
    """
    lowered = (text or "").lower()
    return (
        "bad command name" in lowered
        or "no such item" in lowered
        or "syntax error" in lowered
    )
