"""VCS-style .f filelist parser.

Handles:
    -f <nested_filelist>      recursive inclusion
    +incdir+<path>            include search paths
    +define+<macro>=<value>   global macro definitions
    -y <lib_dir>              library directory
    -v <lib_file>             library file
    // comment  /  # comment  comment lines
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field


@dataclass
class FilelistResult:
    files: list[str] = field(default_factory=list)        # resolved absolute paths
    incdirs: list[str] = field(default_factory=list)       # +incdir+ paths
    defines: dict[str, str] = field(default_factory=dict)  # +define+ macros
    lib_dirs: list[str] = field(default_factory=list)      # -y paths
    lib_files: list[str] = field(default_factory=list)     # -v files
    errors: list[str] = field(default_factory=list)


class FilelistParser:
    """Parse and expand a VCS-style .f filelist."""

    COMMENT_RE = re.compile(r"^\s*(//|#)")
    BLANK_RE = re.compile(r"^\s*$")
    INCDIR_RE = re.compile(r"^\+incdir\+(.*)$")
    DEFINE_RE = re.compile(r"^\+define\+(\w+)(?:=(.*))?$")

    def __init__(self, initial_defines: dict[str, str] | None = None):
        self._defines: dict[str, str] = dict(initial_defines or {})
        self._visited: set[str] = set()  # absolute paths of already-parsed filelists

    # ── public API ───────────────────────────────────────────────────────

    def parse(self, filelist_path: str) -> FilelistResult:
        """Parse a top-level filelist and return the expanded result."""
        self._visited.clear()
        result = self._parse_file(filelist_path)
        # deduplicate while preserving order
        seen: set[str] = set()
        unique_files: list[str] = []
        for f in result.files:
            if f not in seen:
                seen.add(f)
                unique_files.append(f)
        result.files = unique_files
        return result

    # ── internals ────────────────────────────────────────────────────────

    def _parse_file(self, path: str) -> FilelistResult:
        abs_path = os.path.abspath(path)

        # circular reference guard
        if abs_path in self._visited:
            return FilelistResult(errors=[f"Circular filelist reference: {abs_path}"])
        self._visited.add(abs_path)

        if not os.path.isfile(abs_path):
            return FilelistResult(errors=[f"Filelist not found: {abs_path}"])

        base_dir = os.path.dirname(abs_path)
        result = FilelistResult()

        with open(abs_path, "r", encoding="utf-8", errors="replace") as fh:
            for raw_line in fh:
                line = raw_line.rstrip("\n").rstrip("\r")

                if self.BLANK_RE.match(line):
                    continue
                if self.COMMENT_RE.match(line):
                    continue

                line = os.path.expandvars(line)

                # +incdir+
                m = self.INCDIR_RE.match(line)
                if m:
                    incdir = self._resolve_path(m.group(1), base_dir)
                    result.incdirs.append(incdir)
                    continue

                # +define+
                m = self.DEFINE_RE.match(line)
                if m:
                    name, val = m.group(1), m.group(2)
                    self._defines[name] = val if val else ""
                    result.defines[name] = self._defines[name]
                    continue

                # -f <nested filelist>
                if line.startswith("-f ") or line.startswith("-F "):
                    nested_path = line[3:].strip()
                    nested_abs = self._resolve_path(nested_path, base_dir)
                    nested_result = self._parse_file(nested_abs)
                    result.files.extend(nested_result.files)
                    result.incdirs.extend(nested_result.incdirs)
                    result.defines.update(nested_result.defines)
                    result.lib_dirs.extend(nested_result.lib_dirs)
                    result.lib_files.extend(nested_result.lib_files)
                    result.errors.extend(nested_result.errors)
                    continue

                # -y <lib_dir>
                if line.startswith("-y "):
                    lib_dir = self._resolve_path(line[3:].strip(), base_dir)
                    result.lib_dirs.append(lib_dir)
                    continue

                # -v <lib_file>
                if line.startswith("-v "):
                    lib_file = self._resolve_path(line[3:].strip(), base_dir)
                    result.lib_files.append(lib_file)
                    continue

                # ordinary source file
                src_abs = self._resolve_path(line, base_dir)
                result.files.append(src_abs)

        return result

    @staticmethod
    def _resolve_path(target: str, base_dir: str) -> str:
        """Resolve a path relative to base_dir; keep absolute paths as-is."""
        if os.path.isabs(target):
            return os.path.normpath(target)
        return os.path.normpath(os.path.join(base_dir, target))
