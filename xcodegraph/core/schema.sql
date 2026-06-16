-- XCodeGraph SQLite Schema
-- Target: .xcodegraph/index.sqlite

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- ── files ─────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS files (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    path        TEXT    UNIQUE NOT NULL,
    abs_path    TEXT    NOT NULL,
    sha256      TEXT,
    mtime       REAL,
    size        INTEGER,
    language    TEXT    DEFAULT 'systemverilog',
    parse_backend  TEXT DEFAULT 'tree-sitter',
    parse_status   TEXT DEFAULT 'ok',
    parse_warnings TEXT,
    indexed_at  TEXT
);

CREATE INDEX IF NOT EXISTS idx_files_path ON files(path);

-- ── nodes ─────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS nodes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    kind        TEXT    NOT NULL,
    name        TEXT    NOT NULL,
    full_name   TEXT,
    file_id     INTEGER NOT NULL,
    line_start  INTEGER,
    line_end    INTEGER,
    col_start   INTEGER,
    col_end     INTEGER,
    parent_id   INTEGER,
    signature   TEXT,
    attributes_json TEXT,
    FOREIGN KEY (file_id)  REFERENCES files(id)  ON DELETE CASCADE,
    FOREIGN KEY (parent_id) REFERENCES nodes(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_nodes_kind  ON nodes(kind);
CREATE INDEX IF NOT EXISTS idx_nodes_name  ON nodes(name);
CREATE INDEX IF NOT EXISTS idx_nodes_file  ON nodes(file_id);
CREATE INDEX IF NOT EXISTS idx_nodes_full  ON nodes(full_name);

-- ── edges ─────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS edges (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    src_id      INTEGER NOT NULL,
    dst_id      INTEGER NOT NULL,
    kind        TEXT    NOT NULL,
    src_name    TEXT,
    dst_name    TEXT,
    file_id     INTEGER,
    line        INTEGER,
    detail_json TEXT,
    FOREIGN KEY (src_id) REFERENCES nodes(id) ON DELETE CASCADE,
    FOREIGN KEY (dst_id) REFERENCES nodes(id) ON DELETE CASCADE,
    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_edges_src   ON edges(src_id);
CREATE INDEX IF NOT EXISTS idx_edges_dst   ON edges(dst_id);
CREATE INDEX IF NOT EXISTS idx_edges_kind  ON edges(kind);

-- ── unresolved_refs ────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS unresolved_refs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    kind            TEXT    NOT NULL,
    name            TEXT    NOT NULL,
    file_id         INTEGER,
    line            INTEGER,
    context_node_id INTEGER,
    detail_json     TEXT
);

-- ── meta ───────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);

-- ── FTS5 full-text search ──────────────────────────────────────────────

CREATE VIRTUAL TABLE IF NOT EXISTS nodes_fts USING fts5(
    name,
    full_name,
    signature,
    content='nodes',
    content_rowid='id'
);

CREATE TRIGGER IF NOT EXISTS nodes_fts_ai AFTER INSERT ON nodes BEGIN
    INSERT INTO nodes_fts(rowid, name, full_name, signature)
    VALUES (new.id, new.name, new.full_name, new.signature);
END;

CREATE TRIGGER IF NOT EXISTS nodes_fts_ad AFTER DELETE ON nodes BEGIN
    INSERT INTO nodes_fts(nodes_fts, rowid, name, full_name, signature)
    VALUES ('delete', old.id, old.name, old.full_name, old.signature);
END;

CREATE TRIGGER IF NOT EXISTS nodes_fts_au AFTER UPDATE ON nodes BEGIN
    INSERT INTO nodes_fts(nodes_fts, rowid, name, full_name, signature)
    VALUES ('delete', old.id, old.name, old.full_name, old.signature);
    INSERT INTO nodes_fts(rowid, name, full_name, signature)
    VALUES (new.id, new.name, new.full_name, new.signature);
END;

-- ── compilation_units (xcg.md Section 9.1) ─────────────────────────

CREATE TABLE IF NOT EXISTS compilation_units (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    root_file_id  INTEGER NOT NULL,
    root_file_path TEXT NOT NULL,
    filelist_path  TEXT,
    defines_hash   TEXT,
    incdirs_hash   TEXT,
    source_hash    TEXT,
    expanded_hash  TEXT,
    created_at     TEXT,
    updated_at     TEXT,
    FOREIGN KEY (root_file_id) REFERENCES files(id) ON DELETE CASCADE
);

-- ── source_segments (xcg.md Section 9.2) ──────────────────────────

CREATE TABLE IF NOT EXISTS source_segments (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    cu_id             INTEGER NOT NULL,
    virtual_start     INTEGER NOT NULL,
    virtual_end       INTEGER NOT NULL,
    origin_file_id    INTEGER NOT NULL,
    origin_file_path  TEXT NOT NULL,
    origin_start      INTEGER NOT NULL,
    origin_end        INTEGER NOT NULL,
    include_stack_json TEXT,
    FOREIGN KEY (cu_id) REFERENCES compilation_units(id) ON DELETE CASCADE
);

-- ── include_edges (xcg.md Section 9.3) ────────────────────────────

CREATE TABLE IF NOT EXISTS include_edges (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    cu_id             INTEGER NOT NULL,
    from_file_id      INTEGER NOT NULL,
    from_file_path    TEXT NOT NULL,
    to_file_id        INTEGER,
    to_file_path      TEXT,
    include_line      INTEGER NOT NULL,
    include_text      TEXT,
    resolved          INTEGER NOT NULL DEFAULT 1,
    condition         TEXT,
    include_stack_json TEXT,
    FOREIGN KEY (cu_id) REFERENCES compilation_units(id) ON DELETE CASCADE
);

-- ── conditionals (xcg.md Section 9.4) ─────────────────────────────

CREATE TABLE IF NOT EXISTS conditionals (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    cu_id                INTEGER NOT NULL,
    file_id              INTEGER NOT NULL,
    file_path            TEXT NOT NULL,
    line_start           INTEGER NOT NULL,
    line_end             INTEGER NOT NULL,
    directive            TEXT NOT NULL,
    condition            TEXT NOT NULL,
    active               INTEGER NOT NULL,
    active_branch_json   TEXT,
    inactive_branch_json TEXT,
    FOREIGN KEY (cu_id) REFERENCES compilation_units(id) ON DELETE CASCADE
);
