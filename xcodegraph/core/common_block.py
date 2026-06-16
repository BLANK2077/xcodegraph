"""Common block summary hook — pattern-driven common IP detection.

Guides AI agents to avoid diving into common IP internals
(fifo, arbiter, pipeline slice, etc.) unless necessary.
"""

from __future__ import annotations

import re
from typing import Any


class CommonBlockHook:
    """Match file paths against a config of common-block patterns."""

    def __init__(self, config: dict[str, Any]):
        patterns = config.get("patterns", [])
        self._patterns: list[dict] = []
        for p in patterns:
            self._patterns.append({
                "name": p.get("name", ""),
                "regex": re.compile(p.get("path_regex", "")),
                "kind": p.get("kind", ""),
                "summary": p.get("summary", ""),
            })

    def match(self, file_path: str) -> dict[str, str] | None:
        """Return the first matching pattern, or None."""
        for p in self._patterns:
            if p["regex"].match(file_path):
                return {
                    "name": p["name"],
                    "kind": p["kind"],
                    "summary": p["summary"],
                }
        return None

    @staticmethod
    def load_from_file(config_path: str) -> CommonBlockHook:
        """Load patterns from a JSON config file."""
        import json
        with open(config_path, "r", encoding="utf-8") as f:
            return CommonBlockHook(json.load(f))
