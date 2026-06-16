"""SourceManager — include-aware compilation unit builder.

xcg.md Step 3-5: SourceManager + SourceMap + MiniPreprocessor + IncludeResolver.

Builds an expanded virtual source from a compilation unit root file by:
1. Evaluating `ifndef/`ifdef/`elsif/`else/`endif with defines
2. Resolving and expanding `include directives via +incdir+ paths
3. Generating a SourceMap from virtual lines to origin files
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path


# ── data types ────────────────────────────────────────────────────────────

@dataclass
class Diagnostic:
    severity: str  # "warning" | "error"
    message: str
    file: str | None = None
    line: int | None = None


@dataclass
class SourceSegment:
    virtual_start: int
    virtual_end: int
    origin_file: str
    origin_start: int
    origin_end: int
    include_stack: list[str] = field(default_factory=list)


@dataclass
class IncludeEdge:
    from_file: str
    to_file: str | None
    include_line: int
    include_text: str
    resolved: bool
    condition: str | None = None


@dataclass
class ConditionalBlock:
    file: str
    line_start: int
    line_end: int
    directive: str
    condition: str
    active: bool
    active_branch_files: list[str] = field(default_factory=list)
    inactive_branch_files: list[str] = field(default_factory=list)


class SourceMap:
    def __init__(self, segments: list[SourceSegment] | None = None):
        self.segments: list[SourceSegment] = segments or []

    def lookup(self, virtual_line: int) -> SourceSegment | None:
        for seg in self.segments:
            if seg.virtual_start <= virtual_line <= seg.virtual_end:
                return seg
        return None

    def add(self, seg: SourceSegment) -> None:
        self.segments.append(seg)


@dataclass
class ExpandedSource:
    root_file: str
    source_text: str
    source_map: SourceMap
    include_edges: list[IncludeEdge] = field(default_factory=list)
    conditionals: list[ConditionalBlock] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)


# ── MiniPreprocessor ──────────────────────────────────────────────────────

class MiniPreprocessor:
    """Minimal preprocessor for `ifdef/`ifndef/`elsif/`else/`endif.

    Does NOT do full macro expansion — only selects active branch based on defines dict.
    Heavily inspired by VeribleVCSFilelist preprocess.py.
    """

    INCLUDE_RE = re.compile(r'^\s*`include\s+"([^"]+)"')

    def __init__(self, defines: dict[str, str]):
        self.defines: dict[str, str] = dict(defines)
        self.conditional_stack: list[tuple[str, str]] = []
        self.skip_level: int | None = None

    def is_defined(self, macro: str) -> bool:
        return macro in self.defines

    def process_file(self, file_path: str) -> tuple[list[str], list[ConditionalBlock]]:
        """Read a file and process conditional directives. Returns (active_lines, conditionals)."""
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        return self.process_lines(lines, file_path)

    def process_lines(self, lines: list[str], file_label: str) -> tuple[list[str], list[ConditionalBlock]]:
        """Process a list of lines, returning only active lines + conditional metadata."""
        output: list[str] = []
        conditionals: list[ConditionalBlock] = []
        self.conditional_stack = []
        self.skip_level = None

        i = 0
        while i < len(lines):
            stripped = lines[i].strip()

            if stripped.startswith("`ifdef "):
                macro = stripped.split()[1]
                self.conditional_stack.append(("ifdef", macro))
                if self.skip_level is None and macro not in self.defines:
                    self.skip_level = len(self.conditional_stack) - 1
                i += 1
                continue

            if stripped.startswith("`ifndef "):
                macro = stripped.split()[1]
                self.conditional_stack.append(("ifndef", macro))
                if self.skip_level is None and macro in self.defines:
                    self.skip_level = len(self.conditional_stack) - 1
                i += 1
                continue

            if stripped.startswith("`elsif "):
                macro = stripped.split()[1]
                if not self.conditional_stack:
                    raise ValueError(f"`elsif without `ifdef at {file_label}:{i+1}")
                prev_type = self.conditional_stack[-1][0]
                # Only flip if we were in skip mode from the parent ifdef/ifndef and this elsif matches
                if self.skip_level == len(self.conditional_stack) - 1 and macro in self.defines:
                    self.skip_level = None
                elif self.skip_level is None:
                    self.skip_level = len(self.conditional_stack) - 1
                i += 1
                continue

            if stripped == "`else":
                if not self.conditional_stack:
                    raise ValueError(f"`else without `ifdef at {file_label}:{i+1}")
                if self.skip_level is None:
                    self.skip_level = len(self.conditional_stack) - 1
                elif self.skip_level == len(self.conditional_stack) - 1:
                    self.skip_level = None
                i += 1
                continue

            if stripped == "`endif":
                if self.skip_level == len(self.conditional_stack) - 1:
                    self.skip_level = None
                if self.conditional_stack:
                    self.conditional_stack.pop()
                i += 1
                continue

            if self.skip_level is None:
                output.append(lines[i])
            i += 1

        return output, conditionals


# ── SourceManager ─────────────────────────────────────────────────────────

class SourceManager:
    """Build compilation units with include expansion and conditional preprocessing."""

    def __init__(self, incdirs: list[str] | None = None, defines: dict[str, str] | None = None):
        self.incdirs: list[str] = [os.path.abspath(d) for d in (incdirs or [])]
        self._initial_defines: dict[str, str] = dict(defines or {})
        self._visited: set[str] = set()
        self._include_stack: list[str] = []

    def build_compilation_unit(self, root_file: str) -> ExpandedSource:
        """Build expanded source for a compilation unit root file."""
        self._visited.clear()
        self._include_stack.clear()

        root_abs = os.path.abspath(root_file)
        if not os.path.isfile(root_abs):
            return ExpandedSource(
                root_file=root_abs,
                source_text="",
                source_map=SourceMap(),
                diagnostics=[Diagnostic("error", f"File not found: {root_abs}", root_abs)],
            )

        preprocessor = MiniPreprocessor(self._initial_defines)
        active_lines, conditionals = preprocessor.process_file(root_abs)

        source_map = SourceMap()
        include_edges: list[IncludeEdge] = []
        diagnostics: list[Diagnostic] = []
        virtual_lines: list[str] = []

        base_dir = os.path.dirname(root_abs)
        search_dirs = [base_dir] + self.incdirs

        self._expand_impl(
            active_lines, root_abs, base_dir, search_dirs,
            virtual_lines, source_map, include_edges, diagnostics,
        )

        return ExpandedSource(
            root_file=root_abs,
            source_text="\n".join(virtual_lines),
            source_map=source_map,
            include_edges=include_edges,
            conditionals=conditionals,
            diagnostics=diagnostics,
        )

    def _expand_impl(
        self, lines: list[str], current_file: str, base_dir: str,
        search_dirs: list[str],
        virtual_lines: list[str], source_map: SourceMap,
        include_edges: list[IncludeEdge], diagnostics: list[Diagnostic],
    ) -> None:
        for i, line in enumerate(lines):
            m = MiniPreprocessor.INCLUDE_RE.match(line.strip())
            if m:
                filename = m.group(1)
                resolved = self._resolve_include(filename, base_dir, search_dirs)

                include_edges.append(IncludeEdge(
                    from_file=current_file,
                    to_file=resolved,
                    include_line=i + 1,
                    include_text=line.strip(),
                    resolved=resolved is not None,
                ))

                if resolved is None:
                    diagnostics.append(Diagnostic(
                        "warning", f"Unresolved include: {filename}",
                        current_file, i + 1,
                    ))
                    # Insert placeholder comment to preserve line numbering
                    virtual_lines.append(f"// XCODEGRAPH: unresolved include \"{filename}\"")
                    continue

                if resolved in self._visited:
                    diagnostics.append(Diagnostic(
                        "error", f"Circular include: {filename}",
                        current_file, i + 1,
                    ))
                    virtual_lines.append(f"// XCODEGRAPH: circular include \"{filename}\"")
                    continue

                self._visited.add(resolved)

                # Record segment start
                v_start = len(virtual_lines) + 1

                # Read and recursively expand included file
                with open(resolved, "r", encoding="utf-8", errors="replace") as f:
                    included_lines = f.readlines()

                # Preprocess the included file (no additional defines for now)
                inc_preprocessor = MiniPreprocessor(self._initial_defines)
                inc_active, _ = inc_preprocessor.process_lines(included_lines, resolved)

                inc_base = os.path.dirname(resolved)
                self._include_stack.append(resolved)
                self._expand_impl(
                    inc_active, resolved, inc_base, search_dirs,
                    virtual_lines, source_map, include_edges, diagnostics,
                )
                self._include_stack.pop()

                # Record segment
                v_end = len(virtual_lines)
                source_map.add(SourceSegment(
                    virtual_start=v_start,
                    virtual_end=v_end,
                    origin_file=resolved,
                    origin_start=1,
                    origin_end=len(included_lines),
                    include_stack=list(self._include_stack),
                ))
            else:
                virtual_lines.append(line)

    def _resolve_include(self, filename: str, base_dir: str, search_dirs: list[str]) -> str | None:
        """Resolve an include filename against search directories."""
        # 1. Current file directory
        candidate = os.path.normpath(os.path.join(base_dir, filename))
        if os.path.isfile(candidate):
            return candidate

        # 2. +incdir+ paths in order
        for d in search_dirs:
            candidate = os.path.normpath(os.path.join(d, filename))
            if os.path.isfile(candidate):
                return candidate

        return None
