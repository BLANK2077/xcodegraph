"""Indexer — orchestrates filelist expansion + parsing + storage."""

from __future__ import annotations

import os
import time

from .filelist import FilelistParser, FilelistResult
from .parser import SVParser
from .storage import Storage


class Indexer:
    """Top-level indexing pipeline."""

    def __init__(self, db_path: str):
        self.storage = Storage(db_path)
        self.parser = SVParser()
        self.filelist_parser = FilelistParser()

    # ── index entry points ──────────────────────────────────────────────

    def index_filelist(self, filelist_path: str, defines: dict[str, str] | None = None) -> dict:
        """Expand a filelist and index all source files."""
        if defines:
            self.filelist_parser = FilelistParser(defines)

        fl_result = self.filelist_parser.parse(filelist_path)

        t0 = time.time()
        total_nodes = 0
        indexed_files = 0
        errors: list[str] = []

        all_files = list(fl_result.files)

        # Discover include files from +incdir+ paths (.svh/.vh/.sv/.v)
        for incdir in fl_result.incdirs:
            if os.path.isdir(incdir):
                for fn in sorted(os.listdir(incdir)):
                    if self._is_sv_file(fn):
                        inc_path = os.path.join(incdir, fn)
                        if inc_path not in all_files:
                            all_files.append(inc_path)

        for src_path in all_files:
            if self._is_sv_file(src_path):
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
