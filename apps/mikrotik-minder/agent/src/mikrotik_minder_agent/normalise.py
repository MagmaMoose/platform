"""Conservative export normalisation.

RouterOS `/export` output starts with a header line like::

    # 2024-03-15 14:23:45 by RouterOS 7.18.2

If we ship that line straight to git, every export run produces a one-line diff
even when nothing actually changed — so we'd flood operators with drift alerts.
We strip *only* that line and leave the rest verbatim. More aggressive scrubbing
(e.g. wireguard endpoints, neighbor discovery state) is opt-in via future flags.
"""

from __future__ import annotations

import re

_TIMESTAMP_HEADER = re.compile(
    r"^#\s*\d{4}-\d{2}-\d{2}\s+\d{1,2}:\d{2}:\d{2}\s+by\s+RouterOS\s+\S+\s*$",
)


def normalise_export(text: str) -> str:
    """Strip RouterOS' volatile timestamp header. Returns text ending in a newline."""
    if not text:
        return ""
    lines = text.splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)
    if lines and _TIMESTAMP_HEADER.match(lines[0]):
        lines.pop(0)
    body = "\n".join(lines).rstrip()
    return body + "\n" if body else ""
