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
