"""Machine-readable output helpers.

Rich's ``print`` (``from rich import print``) wraps text at the detected terminal
width, which hard-inserts newlines **inside** long JSON string values and long
log lines. That silently corrupts machine-readable output — a downstream
``json.load`` fails with "Invalid control character", and a replayed log line no
longer matches what ComfyUI actually wrote.

Everything that is meant to be consumed by a script, an agent, or replayed
verbatim must therefore bypass rich and go through one of these helpers.
"""

from __future__ import annotations

import json
import sys


def emit_json(payload, *, indent: int | None = None) -> None:
    """Write ``payload`` as JSON to stdout, bypassing rich's line wrapping."""
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=indent) + "\n")
    sys.stdout.flush()


def emit_raw(text: str) -> None:
    """Write ``text`` to stdout verbatim, bypassing rich's line wrapping."""
    sys.stdout.write(text)
    sys.stdout.flush()
