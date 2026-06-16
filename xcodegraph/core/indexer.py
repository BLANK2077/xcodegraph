"""Indexer — orchestrates filelist expansion + parsing + storage."""

from __future__ import annotations

import os
import time

from .filelist import FilelistParser, FilelistResult
from .parser import SVParser
from .source_manager import SourceManager
from .storage import Storage


class Indexer:
    """Top-level indexing pipeline."""

    def __init__(self, db_path: str):
        self.storage = Storage(db_path)
        self.parser = SVParser()
        self.filelist_parser = FilelistParser()

    # ── index entry points ──────────────────────────────────────────────

    def index_filelist(self, filelist_path: str, defines: dict[str, str] | None = None,
                       expand_includes: bool = False) -> dict:
        """Expand a filelist and index all source files."""
        if defines:
            self.filelist_parser = FilelistParser(defines)

        fl_result = self.filelist_parser.parse(filelist_path)

        t0 = time.time()
        total_nodes = 0
        indexed_files = 0
        errors: list[str] = []

        # xcg.md Step 2: +incdir+ is only include search path, NOT source list.
        all_files = list(fl_result.files)

        # xcg.md Step 3-5: Include-aware compilation unit expansion
        source_manager = None
        if expand_includes:
            source_manager = SourceManager(
                incdirs=fl_result.incdirs,
                defines=fl_result.defines,
            )

        for src_path in all_files:
            if self._is_sv_file(src_path):
                if self._is_header(src_path) and not expand_includes:
                    continue  # xcg.md: .svh/.vh in filelist → warning, skip

                try:
                    if source_manager:
                        # Build expanded compilation unit
                        expanded = source_manager.build_compilation_unit(src_path)
                        if expanded.diagnostics:
                            for d in expanded.diagnostics:
                                if d.severity == "error":
                                    errors.append(f"{src_path}: {d.message}")
                        source = expanded.source_text
                        file_rec = self.storage.upsert_file(src_path, source.encode("utf-8"))
                        result = self.parser.extract(src_path, source)
                    else:
                        with open(src_path, "r", encoding="utf-8", errors="replace") as f:
                            source = f.read()
                        file_rec = self.storage.upsert_file(src_path, source.encode("utf-8"))
                        result = self.parser.extract(src_path, source)

                    self.storage.store_extraction(file_rec, result)
                    total_nodes += len(result.nodes)
                    indexed_files += 1
                    errors.extend(result.errors)
                except Exception as e:
                    errors.append(f"{src_path}: {e}")

        # Save meta
        self.storage.set_meta("filelist_path", filelist_path)
        self.storage.set_meta("filelist_hash", "")
        self.storage.set_meta("created_at", time.strftime("%Y-%m-%dT%H:%M:%S"))
        self.storage.set_meta("updated_at", time.strftime("%Y-%m-%dT%H:%M:%S"))
        self.storage.set_meta("backend", "tree-sitter")
        self.storage.set_meta("schema_version", "1")
        # Record git HEAD for stale detection
        self._record_git_head()

        return {
            "indexed_files": indexed_files,
            "total_nodes": total_nodes,
            "errors": errors,
            "incdirs": fl_result.incdirs,
            "defines": fl_result.defines,
            "duration_ms": (time.time() - t0) * 1000,
        }

    def index_directory(self, root_dir: str) -> dict:
        """Scan a directory recursively and index all SV files."""
        t0 = time.time()
        total_nodes = 0
        indexed_files = 0
        errors: list[str] = []

        for dirpath, _dirs, filenames in os.walk(root_dir):
            for fn in filenames:
                if self._is_sv_file(fn):
                    src_path = os.path.join(dirpath, fn)
                    try:
                        with open(src_path, "r", encoding="utf-8", errors="replace") as f:
                            source = f.read()
                        file_rec = self.storage.upsert_file(src_path, source.encode("utf-8"))
                        result = self.parser.extract(src_path, source)
                        self.storage.store_extraction(file_rec, result)
                        total_nodes += len(result.nodes)
                        indexed_files += 1
                        errors.extend(result.errors)
                    except Exception as e:
                        errors.append(f"{src_path}: {e}")

        self.storage.set_meta("updated_at", time.strftime("%Y-%m-%dT%H:%M:%S"))

        return {
            "indexed_files": indexed_files,
            "total_nodes": total_nodes,
            "errors": errors,
            "duration_ms": (time.time() - t0) * 1000,
        }

    @staticmethod
    def _is_sv_file(path: str) -> bool:
        ext = os.path.splitext(path)[1].lower()
        return ext in (".sv", ".svh", ".v", ".vh", ".sva")

    @staticmethod
    def _is_header(path: str) -> bool:
        ext = os.path.splitext(path)[1].lower()
        return ext in (".svh", ".vh")

    def close(self) -> None:
        self.storage.close()

    def resolve_references(self) -> dict:
        """Run cross-file reference resolution. Returns {total, resolved, remaining}."""
        from .resolver import ReferenceResolver
        r = ReferenceResolver()
        return r.resolve(self.storage)

    def _record_git_head(self) -> None:
        """Record current git HEAD for stale detection."""
        import subprocess
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                head = result.stdout.strip()
                self.storage.set_meta("git_head", head)
                # Also get branch
                branch = subprocess.run(
                    ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                    capture_output=True, text=True, timeout=5,
                )
                if branch.returncode == 0:
                    self.storage.set_meta("git_branch", branch.stdout.strip())
        except Exception:
            pass  # not a git repo or git not available
