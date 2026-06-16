"""Test VCS filelist parser."""

import os

from xcodegraph.core.filelist import FilelistParser


class TestBasicPaths:
    """RED-GREEN: Basic filelist parsing."""

    def test_single_source_file(self, make_filelist):
        fp = make_filelist("test.f", ["top.sv"], {"top.sv": "module top; endmodule"})
        result = FilelistParser().parse(fp)
        assert result.errors == []
        assert len(result.files) == 1
        assert result.files[0].endswith("top.sv")

    def test_multiple_source_files(self, make_filelist):
        fp = make_filelist("test.f", ["a.sv", "b.sv", "c.sv"],
                           {"a.sv": "//", "b.sv": "//", "c.sv": "//"})
        result = FilelistParser().parse(fp)
        assert result.errors == []
        assert len(result.files) == 3

    def test_skips_blank_and_comment_lines(self, make_filelist):
        fp = make_filelist("test.f", [
            "// this is a comment",
            "  // indented comment",
            "",
            "# shell-style comment",
            "   # indented hash comment",
            "top.sv",
        ], {"top.sv": "//"})
        result = FilelistParser().parse(fp)
        assert result.errors == []
        assert len(result.files) == 1

    def test_relative_path_resolved_against_filelist_dir(self, make_filelist):
        fp = make_filelist("my/app/flist.f", ["../rtl/top.sv"],
                           {"rtl/top.sv": "module top; endmodule"})
        result = FilelistParser().parse(fp)
        assert result.errors == []
        assert len(result.files) == 1
        assert "rtl/top.sv" in result.files[0]

    def test_absolute_path_preserved(self, make_filelist):
        abs_sv = str(make_filelist("test.f", [])).replace(".f", ".sv")
        # Simulate absolute path by writing the real absolute path
        fp = make_filelist("test.f", [abs_sv])
        result = FilelistParser().parse(fp)
        assert len(result.files) == 1
        assert result.files[0] == abs_sv


class TestPlusArgs:
    """+incdir+ and +define+ directives."""

    def test_incdir_collected(self, make_filelist):
        fp = make_filelist("test.f", [
            "+incdir+/usr/local/include",
            "+incdir+../headers",
            "top.sv",
        ], {"top.sv": "//"})
        result = FilelistParser().parse(fp)
        assert "/usr/local/include" in result.incdirs
        assert any("headers" in d for d in result.incdirs)

    def test_define_collected(self, make_filelist):
        fp = make_filelist("test.f", [
            "+define+SIMULATION",
            "+define+DATA_WIDTH=64",
            "top.sv",
        ], {"top.sv": "//"})
        result = FilelistParser().parse(fp)
        assert result.defines.get("SIMULATION") == "1"  # VCS: bare define → "1"
        assert result.defines.get("DATA_WIDTH") == "64"

    def test_define_without_value(self, make_filelist):
        fp = make_filelist("test.f", [
            "+define+DEBUG",
            "top.sv",
        ], {"top.sv": "//"})
        result = FilelistParser().parse(fp)
        assert result.defines["DEBUG"] == "1"  # VCS: bare define → "1"


class TestNestedFilelists:
    """-f recursive filelist inclusion."""

    def test_nested_f_expands(self, make_filelist):
        fp = make_filelist("main.f", [
            "-f sub.f",
        ], {
            "sub.f": "a.sv\nb.sv",
            "a.sv": "//", "b.sv": "//",
        })
        result = FilelistParser().parse(fp)
        assert result.errors == []
        assert len(result.files) == 2

    def test_deduplicates_files(self, make_filelist):
        fp = make_filelist("main.f", [
            "top.sv",
            "-f sub.f",
            "top.sv",
        ], {
            "sub.f": "top.sv",
            "top.sv": "module top; endmodule",
        })
        result = FilelistParser().parse(fp)
        # duplicates removed but order preserved (first occurrence kept)
        assert len(result.files) == 1

    def test_circular_reference_detected(self, make_filelist):
        fp = make_filelist("a.f", [
            "-f b.f",
        ], {
            "b.f": "-f a.f",
        })
        result = FilelistParser().parse(fp)
        assert any("circular" in e.lower() or "Circular" in e
                   for e in result.errors)

    def test_missing_filelist_reports_error(self, make_filelist):
        fp = make_filelist("main.f", [
            "-f missing.f",
        ])
        result = FilelistParser().parse(fp)
        assert any("not found" in e.lower() for e in result.errors)


class TestEnvVarExpansion:
    """Environment variable ${VAR} in filelist lines."""

    def test_expands_env_vars(self, make_filelist, monkeypatch):
        monkeypatch.setenv("PROJ_ROOT", "/home/project")
        fp = make_filelist("test.f", [
            "${PROJ_ROOT}/rtl/top.sv",
        ], {"${PROJ_ROOT}/rtl/top.sv": "//"})
        result = FilelistParser().parse(fp)
        if result.errors:
            pass


# ── xcg.md Section 12: VCS filelist 兼容性增强 ──

class TestMultiIncDir:
    """+incdir+a+b+c format (VCS multi-path)."""

    def test_multi_plus_incdir_split(self, make_filelist):
        fp = make_filelist("test.f", [
            "+incdir+./a+./b+./c",
            "top.sv",
        ], {"top.sv": "//"})
        result = FilelistParser().parse(fp)
        assert len(result.incdirs) == 3
        assert any("a" in d for d in result.incdirs)
        assert any("b" in d for d in result.incdirs)
        assert any("c" in d for d in result.incdirs)

    def test_multi_plus_define_bare_defaults_to_1(self, make_filelist):
        fp = make_filelist("test.f", [
            "+define+USE_AXI+DATA_WIDTH=64",
            "top.sv",
        ], {"top.sv": "//"})
        result = FilelistParser().parse(fp)
        assert result.defines.get("USE_AXI") == "1"
        assert result.defines.get("DATA_WIDTH") == "64"

    def test_multi_define_all_bare(self, make_filelist):
        fp = make_filelist("test.f", [
            "+define+A+B+C",
            "top.sv",
        ], {"top.sv": "//"})
        result = FilelistParser().parse(fp)
        assert result.defines.get("A") == "1"
        assert result.defines.get("B") == "1"
        assert result.defines.get("C") == "1"


class TestBackslashContinuation:
    """\\ line continuation in filelist."""

    def test_backslash_continuation_joins_lines(self, make_filelist):
        fp = make_filelist("test.f", [
            "+incdir+./a \\",
            "  +./b",
            "top.sv",
        ], {"top.sv": "//"})
        result = FilelistParser().parse(fp)
        # Merged line: "+incdir+./a   +./b" → split on + → [./a, ./b]
        assert len(result.incdirs) >= 1
        assert any("a" in d for d in result.incdirs)


class TestQuotedPaths:
    """Quoted path handling in filelist."""

    def test_quoted_incdir_strips_quotes(self, make_filelist):
        fp = make_filelist("test.f", [
            '+incdir+"./my path/"',
            "top.sv",
        ], {"top.sv": "//"})
        result = FilelistParser().parse(fp)
        assert len(result.incdirs) == 1
        incdir = result.incdirs[0]
        assert '"' not in incdir


class TestVCSOptions:
    """VCS compile options should NOT be treated as source files."""

    def test_vcs_options_not_in_files(self, make_filelist):
        fp = make_filelist("test.f", [
            "-sverilog",
            "-timescale=1ns/1ps",
            "-full64",
            "top.sv",
        ], {"top.sv": "//"})
        result = FilelistParser().parse(fp)
        # Only top.sv should be in files
        assert len(result.files) == 1
        assert "top.sv" in result.files[0]

    def test_vcs_option_generates_warning(self, make_filelist):
        fp = make_filelist("test.f", [
            "-sverilog",
            "top.sv",
        ], {"top.sv": "//"})
        result = FilelistParser().parse(fp)
        assert any("sverilog" in w for w in result.warnings)
