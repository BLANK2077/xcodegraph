"""VCS-style .f filelist parser.

Handles:
    -f <nested_filelist>      recursive inclusion
    +incdir+<path>[+<path>]   include search paths (VCS multi-path)
    +define+<macro>[=val][+<macro>[=val]]  global macro definitions
    -y <lib_dir>              library directory
    -v <lib_file>             library file
    // comment  /  # comment  comment lines
    \\          backslash line continuation
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

# ── VCS compile options to ignore (not source files) ──────────────────────

VCS_OPTIONS = re.compile(
    r'^[-+]('
    r'sverilog|v2k|sv|'
    r'timescale|override_timescale|'
    r'full64|cpp|cc|'
    r'lca|kdb|debug_access|debug_access\+all|'
    r'debug_region|debug|vcs|'
    r'assert|cm|cov|cm_dir|cm_name|'
    r'f|F|file|'
    r'plusarg_save|vcs|'
    r'ntb_opts|'
    r'ignore|'
    r'error|warn|fatal|'
    r'notice|nbaopt|'
    r'line|debug_all|'
    r'P|Mdir|Mlib|'
    r'vera|'
    r'l|R|u|'
    r'override|'
    r'hera|hera_cm|'
    r'fsdb|fsdb_dir|'
    r'kdb|kdb_dir|'
    r'vpd|vpd_dir|'
    r'vpdtoggle|vpdtoggle_dir|'
    r'sdf|sdfmin|sdftyp|sdfmax|'
    r'lib|liblist|'
    r'y|v|'
    r'o|'
    r'id|'
    r'cm_assert|cm_cond|cm_tgl|cm_fsm|cm_glitch|cm_line|cm_branch'
    r')'
)


@dataclass
class FilelistResult:
    files: list[str] = field(default_factory=list)
    incdirs: list[str] = field(default_factory=list)
    defines: dict[str, str] = field(default_factory=dict)
    lib_dirs: list[str] = field(default_factory=list)
    lib_files: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class FilelistParser:
    """Parse and expand a VCS-style .f filelist."""

    COMMENT_RE = re.compile(r"^\s*(//|#)")
    BLANK_RE = re.compile(r"^\s*$")
    INCDIR_RE = re.compile(r"^\+incdir\+(.+)$")
    DEFINE_RE = re.compile(r"^\+define\+(.+)$")
    CONT_RE = re.compile(r"^(.*?)\s*\\\s*$")

    def __init__(self, initial_defines: dict[str, str] | None = None):
        self._defines: dict[str, str] = dict(initial_defines or {})
        self._visited: set[str] = set()

    # ── public API ───────────────────────────────────────────────────────

    def parse(self, filelist_path: str) -> FilelistResult:
        self._visited.clear()
        result = self._parse_file(filelist_path)
        seen: set[str] = set()
        unique_files: list[str] = []
        for f in result.files:
            if f not in seen:
                seen.add(f)
                unique_files.append(f)
        result.files = unique_files
        return result

    # ── internals ────────────────────────────────────────────────────────

    def _read_lines(self, abs_path: str) -> list[tuple[str, int]]:
        """Read lines from a file, handling backslash continuation."""
        with open(abs_path, "r", encoding="utf-8", errors="replace") as fh:
            raw_lines = fh.readlines()

        merged: list[tuple[str, int]] = []
        i = 0
        while i < len(raw_lines):
            line = raw_lines[i].rstrip("\n").rstrip("\r")
            m = self.CONT_RE.match(line)
            if m:
                # backslash continuation: merge with next line
                prefix = m.group(1)
                if i + 1 < len(raw_lines):
                    next_line = raw_lines[i + 1].rstrip("\n").rstrip("\r")
                    line = prefix + " " + next_line.lstrip()
                    i += 1
            merged.append((line, i + 1))
            i += 1

        return merged

    def _parse_file(self, path: str) -> FilelistResult:
        abs_path = os.path.abspath(path)

        if abs_path in self._visited:
            return FilelistResult(errors=[f"Circular filelist reference: {abs_path}"])
        self._visited.add(abs_path)

        if not os.path.isfile(abs_path):
            return FilelistResult(errors=[f"Filelist not found: {abs_path}"])

        base_dir = os.path.dirname(abs_path)
        result = FilelistResult()

        for raw_line, _lineno in self._read_lines(abs_path):
            line = raw_line.rstrip("\n").rstrip("\r")

            if self.BLANK_RE.match(line):
                continue
            if self.COMMENT_RE.match(line):
                continue

            line = os.path.expandvars(line)

            # +incdir+<path>[+<path>...]
            m = self.INCDIR_RE.match(line)
            if m:
                parts = m.group(1).split("+")
                rest_parts: list[str] = []
                for part in parts:
                    part = part.strip()
                    if not part:
                        continue
                    candidate = self._resolve_path(part.strip('"'), base_dir)
                    if os.path.isdir(candidate) or "/" in part or "\\" in part:
                        result.incdirs.append(candidate)
                    else:
                        rest_parts.append(part)
                for rp in rest_parts:
                    result.files.append(self._resolve_path(rp.strip('"'), base_dir))
                continue

            # +define+<macro>[=val][+<macro>[=val]...]
            m = self.DEFINE_RE.match(line)
            if m:
                for token in m.group(1).split("+"):
                    token = token.strip()
                    if not token:
                        continue
                    if "=" in token:
                        name, val = token.split("=", 1)
                        self._defines[name] = val
                        result.defines[name] = val
                    else:
                        self._defines[token] = "1"
                        result.defines[token] = "1"
                continue

            # -f <nested filelist>
            if line.startswith("-f ") or line.startswith("-F "):
                nested_path = line[3:].strip().strip('"')
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
                lib_dir = self._resolve_path(line[3:].strip().strip('"'), base_dir)
                result.lib_dirs.append(lib_dir)
                continue

            # -v <lib_file>
            if line.startswith("-v "):
                lib_file = self._resolve_path(line[3:].strip().strip('"'), base_dir)
                result.lib_files.append(lib_file)
                continue

            # VCS compile option → warn, not source file
            if VCS_OPTIONS.match(line.strip()):
                result.warnings.append(f"Ignored compile option: {line.strip()}")
                continue

            # Ordinary source file
            src_abs = self._resolve_path(line.strip().strip('"'), base_dir)
            result.files.append(src_abs)

        return result

    @staticmethod
    def _resolve_path(target: str, base_dir: str) -> str:
        if os.path.isabs(target):
            return os.path.normpath(target)
        return os.path.normpath(os.path.join(base_dir, target))
