"""Storage and indexing.

The Markdown files under `memory_dir` are the source of truth. The SQLite
database is a disposable index built from them: full text (FTS5), the graph of
hand-written [[links]], chunks and their embeddings. Delete it and run
`hippocampus sync --full` to rebuild it from scratch.
"""
import re
import sqlite3
import threading
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

STATUSES = ("active", "pending", "resolved", "superseded")
# Memory files written in Portuguese (the project's first language) keep working.
STATUS_ALIASES = {"ativa": "active", "pendente": "pending",
                  "resolvida": "resolved", "substituida": "superseded"}
TYPES = ("project", "reference", "feedback", "user")
SKIP_FILES = {"MEMORY.md", "README.md"}
LINK_RE = re.compile(r"\[\[([^\]]+)\]\]")

SCHEMA = """
CREATE TABLE IF NOT EXISTS memories(
  id INTEGER PRIMARY KEY, name TEXT, path TEXT UNIQUE, project TEXT,
  description TEXT, type TEXT, modified TEXT, body TEXT,
  status TEXT DEFAULT 'active', status_at TEXT);
CREATE INDEX IF NOT EXISTS ix_mem_name ON memories(name);
CREATE VIRTUAL TABLE IF NOT EXISTS fts USING fts5(name, description, body,
  tokenize="unicode61 remove_diacritics 2");
CREATE TABLE IF NOT EXISTS links(memory_id INTEGER, source TEXT, target TEXT,
  resolved INTEGER);
CREATE INDEX IF NOT EXISTS ix_links_src ON links(source);
CREATE INDEX IF NOT EXISTS ix_links_dst ON links(target);
CREATE INDEX IF NOT EXISTS ix_links_mem ON links(memory_id);
CREATE TABLE IF NOT EXISTS chunks(id INTEGER PRIMARY KEY, memory_id INTEGER, text TEXT);
CREATE INDEX IF NOT EXISTS ix_chunks_mem ON chunks(memory_id);
CREATE TABLE IF NOT EXISTS vectors(chunk_id INTEGER PRIMARY KEY, v BLOB);
CREATE TABLE IF NOT EXISTS suggestions(a TEXT, b TEXT, sim REAL);
CREATE INDEX IF NOT EXISTS ix_sug_a ON suggestions(a);
CREATE INDEX IF NOT EXISTS ix_sug_b ON suggestions(b);
"""


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def slug(s):
    """Memory names are ASCII slugs: `Acesso ao Banco` -> `acesso-ao-banco`."""
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def clean_project(p):
    return re.sub(r"[^A-Za-z0-9_-]+", "-", p or "general").strip("-") or "general"


def project_from_path(rel):
    """First folder of the relative path. Claude Code names its per-project
    folders after the absolute path (`C--Work-foo`); the drive prefix is noise."""
    return re.sub(r"^[A-Za-z]--", "", Path(rel).parts[0]) if len(Path(rel).parts) > 1 \
        else "general"


def normalize_status(s):
    s = (s or "").strip().lower()
    return STATUS_ALIASES.get(s, s)


def parse_md(text):
    """Minimal front matter parser: flat `key: value` lines, nesting ignored.

    It accepts Claude Code's own memory format (`name`, `description`,
    `metadata.type`) so its memory folders can be synced as they are."""
    meta, body = {}, text
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end > 0:
            body = text[end + 4:].lstrip("\n")
            for line in text[3:end].splitlines():
                m = re.match(r"^\s{0,2}([a-zA-Z_]+):\s*(.*)$", line)
                if m and m.group(2).strip():
                    meta[m.group(1)] = m.group(2).strip().strip('"').strip("'")
    if "status_em" in meta and "status_at" not in meta:
        meta["status_at"] = meta["status_em"]
    return meta, body


def render_md(rec):
    desc = " ".join((rec["description"] or "").split()).replace('"', "'")
    lines = ["---", "name: " + rec["name"], 'description: "' + desc + '"', "metadata:",
             "  node_type: memory", "  type: " + rec["type"],
             "  modified: " + rec["modified"], "  status: " + rec["status"]]
    if rec.get("status_at"):
        lines.append("  status_at: " + rec["status_at"])
    return "\n".join(lines) + "\n---\n\n" + rec["body"].strip() + "\n"


def chunk(body, limit=1400):
    """Split on `## ` headings, then on blank lines when a section is too long.

    Indexing by section instead of by file matters: a long memory about a
    server has one paragraph about the database and one about backups, and a
    single vector for the whole file ends up close to neither."""
    parts, cur = [], []
    for line in body.splitlines():
        if line.startswith("## ") and cur:
            parts.append("\n".join(cur))
            cur = []
        cur.append(line)
    if cur:
        parts.append("\n".join(cur))
    out = []
    for p in parts:
        p = p.strip()
        while len(p) > limit:
            cut = p.rfind("\n\n", 0, limit)
            cut = cut if cut > 300 else limit
            out.append(p[:cut].strip())
            p = p[cut:].strip()
        if p:
            out.append(p)
    return out or ["(empty)"]


class Embedder:
    """Lazy wrapper around fastembed. Runs locally on ONNX: nothing leaves the box."""

    def __init__(self, model):
        self.model_name = model
        self._model = None
        self._lock = threading.Lock()

    def __call__(self, texts):
        with self._lock:
            if self._model is None:
                from fastembed import TextEmbedding
                self._model = TextEmbedding(model_name=self.model_name)
        vs = np.asarray(list(self._model.embed(list(texts), batch_size=16)), dtype="float32")
        return vs / (np.linalg.norm(vs, axis=1, keepdims=True) + 1e-9)


class Store:
    def __init__(self, cfg, embedder=None):
        self.cfg = cfg
        self.embed = embedder or Embedder(cfg.model)
        self.vectors = {"ids": None, "m": None}
        cfg.memory_dir.mkdir(parents=True, exist_ok=True)
        cfg.db_path.parent.mkdir(parents=True, exist_ok=True)
        c = self.connect()
        c.executescript(SCHEMA)
        c.close()

    # -- plumbing ---------------------------------------------------------

    def connect(self):
        c = sqlite3.connect(self.cfg.db_path, check_same_thread=False, timeout=30)
        c.row_factory = sqlite3.Row
        return c

    def load_vectors(self):
        c = self.connect()
        rows = c.execute("SELECT chunk_id, v FROM vectors ORDER BY chunk_id").fetchall()
        c.close()
        if not rows:
            self.vectors = {"ids": np.array([], dtype=int), "m": None}
            return
        self.vectors = {"ids": np.array([r["chunk_id"] for r in rows], dtype=int),
                        "m": np.vstack([np.frombuffer(r["v"], dtype="float32") for r in rows])}

    def embed_memory(self, rec):
        rec["chunks"] = chunk(rec["body"])
        rec["vectors"] = self.embed(
            [(rec["name"] + " | " + (rec["description"] or "") + "\n" + p)[:2000]
             for p in rec["chunks"]])

    def _upsert(self, c, rec, known):
        """Write one embedded memory into the index. Identity is the FILE, not the
        name: the same name may legitimately exist in two projects, and keying
        by name meant one of the two rows was silently never updated."""
        row = c.execute("SELECT id FROM memories WHERE path=?", (rec["path"],)).fetchone()
        cols = (rec["name"], rec["path"], rec["project"], rec["description"], rec["type"],
                rec["modified"], rec["body"], rec["status"], rec.get("status_at"))
        if row:
            mid = row["id"]
            c.execute("UPDATE memories SET name=?,path=?,project=?,description=?,type=?,"
                      "modified=?,body=?,status=?,status_at=? WHERE id=?", cols + (mid,))
            self._drop_derived(c, mid)
        else:
            mid = c.execute("INSERT INTO memories(name,path,project,description,type,"
                            "modified,body,status,status_at) VALUES(?,?,?,?,?,?,?,?,?)",
                            cols).lastrowid
        c.execute("INSERT INTO fts(rowid,name,description,body) VALUES(?,?,?,?)",
                  (mid, rec["name"], rec["description"], rec["body"]))
        for target in {slug(x) for x in LINK_RE.findall(rec["body"])}:
            c.execute("INSERT INTO links VALUES(?,?,?,?)",
                      (mid, rec["name"], target, 1 if target in known else 0))
        c.execute("UPDATE links SET resolved=1 WHERE target=?", (rec["name"],))
        for text, v in zip(rec["chunks"], rec["vectors"], strict=True):
            cid = c.execute("INSERT INTO chunks(memory_id,text) VALUES(?,?)",
                            (mid, text)).lastrowid
            c.execute("INSERT INTO vectors VALUES(?,?)",
                      (cid, np.asarray(v, dtype="float32").tobytes()))
        return mid

    @staticmethod
    def _drop_derived(c, mid):
        c.execute("DELETE FROM fts WHERE rowid=?", (mid,))
        c.execute("DELETE FROM vectors WHERE chunk_id IN "
                  "(SELECT id FROM chunks WHERE memory_id=?)", (mid,))
        c.execute("DELETE FROM chunks WHERE memory_id=?", (mid,))
        c.execute("DELETE FROM links WHERE memory_id=?", (mid,))

    def _record_from_file(self, path, rel, previous_status=None):
        meta, body = parse_md(path.read_text(encoding="utf-8", errors="replace"))
        # A file without `status` (e.g. written by a local session) must NOT
        # downgrade what the server already marked: it inherits the indexed one.
        status = normalize_status(meta.get("status")) or previous_status or "active"
        if status not in STATUSES:
            status = "active"
        return {"name": slug(meta.get("name") or path.stem), "path": rel,
                "project": project_from_path(rel), "body": body,
                "description": meta.get("description", ""),
                "type": meta.get("type", "project"), "modified": meta.get("modified", ""),
                "status": status, "status_at": meta.get("status_at")}

    # -- sync -------------------------------------------------------------

    def sync(self, full=False, log=print):
        """Bring the index in line with the Markdown files.

        Only new or changed files are embedded, so a routine sync takes
        seconds. `full=True` wipes the index first (minutes, emergencies only)."""
        root = self.cfg.memory_dir
        c = self.connect()
        if full:
            for t in ("memories", "fts", "links", "chunks", "vectors", "suggestions"):
                c.execute("DELETE FROM " + t)
            c.commit()
        indexed = {r["path"]: r for r in c.execute(
            "SELECT id, name, path, modified, body, status FROM memories")}
        files = {str(p.relative_to(root)).replace("\\", "/"): p
                 for p in sorted(root.rglob("*.md")) if p.name not in SKIP_FILES}

        # Prune: a file removed from disk leaves the index too. Without this a
        # deleted duplicate kept showing up in search results.
        gone = [r for rel, r in indexed.items() if rel not in files]
        for r in gone:
            self._drop_derived(c, r["id"])
            c.execute("DELETE FROM memories WHERE id=?", (r["id"],))
            c.execute("UPDATE links SET resolved=0 WHERE target=? AND NOT EXISTS "
                      "(SELECT 1 FROM memories WHERE name=?)", (r["name"], r["name"]))
            log("  pruned " + r["path"])
        c.commit()

        todo = []
        for rel, path in files.items():
            old = indexed.get(rel)
            rec = self._record_from_file(path, rel, old["status"] if old else None)
            # date AND body: a corrected copy of a file can keep the same
            # `modified`, so the date alone misses the change
            if old and old["modified"] == rec["modified"] and \
                    (old["body"] or "").strip() == rec["body"].strip() and \
                    old["status"] == rec["status"]:
                continue
            rec["action"] = "update" if old else "new"
            todo.append(rec)

        if not todo:
            c.close()
            return {"changed": 0, "pruned": len(gone), **self.stats()}

        for rec in todo:
            log("  %-6s %s  (%s)" % (rec["action"], rec["name"], rec["project"]))
        # Embed everything BEFORE opening the write transaction: embedding is
        # slow, and holding the write lock meanwhile made the server's own
        # writes fail with "database is locked".
        for rec in todo:
            self.embed_memory(rec)
        known = {r[0] for r in c.execute("SELECT name FROM memories")} | \
            {r["name"] for r in todo}
        for rec in todo:
            self._upsert(c, rec, known)
        c.commit()
        c.close()
        self.load_vectors()
        return {"changed": len(todo), "pruned": len(gone), **self.stats()}

    def stats(self):
        c = self.connect()
        q = lambda sql: c.execute(sql).fetchone()[0]  # noqa: E731
        out = {"memories": q("SELECT COUNT(*) FROM memories"),
               "chunks": q("SELECT COUNT(*) FROM chunks"),
               "links": q("SELECT COUNT(*) FROM links WHERE resolved=1"),
               "broken_links": q("SELECT COUNT(*) FROM links WHERE resolved=0"),
               "pending": q("SELECT COUNT(*) FROM memories WHERE status='pending'")}
        c.close()
        return out

    # -- write ------------------------------------------------------------

    def save(self, name, description, body, type="project", project="general", status=None):
        name, project = slug(name), clean_project(project)
        if not name or not (body or "").strip():
            return {"error": "name and body are required"}
        if type not in TYPES:
            type = "project"
        now = now_iso()
        c = self.connect()
        old = c.execute("SELECT path, status, status_at FROM memories WHERE name=? AND project=?",
                        (name, project)).fetchone()
        c.close()
        if status:
            status = normalize_status(status)
            if status not in STATUSES:
                return {"error": "invalid status, use one of: " + ", ".join(STATUSES)}
            status_at = now if not old or old["status"] != status else old["status_at"]
        else:  # not given: keep whatever the memory already had
            status, status_at = (old["status"], old["status_at"]) if old else ("active", None)

        # Rewrite the file where it already lives, so existing folder layouts survive.
        rel = old["path"] if old else project + "/" + name + ".md"
        rec = {"name": name, "path": rel, "project": project, "description": description or "",
               "type": type, "modified": now, "body": body.strip(), "status": status,
               "status_at": status_at}
        path = self.cfg.memory_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_md(rec), encoding="utf-8")

        self.embed_memory(rec)
        c = self.connect()
        known = {r[0] for r in c.execute("SELECT name FROM memories")} | {name}
        self._upsert(c, rec, known)
        c.commit()
        c.close()
        self.load_vectors()
        return {"ok": True, "name": name, "path": rel, "chunks": len(rec["chunks"]),
                "status": status}

    def import_file(self, rel, content):
        """Receive a raw Markdown file from a client (the sync hook) and index it."""
        rel = rel.replace("\\", "/").lstrip("/")
        path = (self.cfg.memory_dir / rel).resolve()
        if self.cfg.memory_dir.resolve() not in path.parents or path.suffix != ".md":
            return {"error": "invalid path"}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return {"ok": True, "path": rel}

    def mark(self, name, status, note=""):
        """Change a memory's status and append the reason, dated, to its body."""
        status = normalize_status(status)
        if status not in STATUSES:
            return {"error": "invalid status, use one of: " + ", ".join(STATUSES)}
        c = self.connect()
        r = c.execute("SELECT * FROM memories WHERE name=? ORDER BY modified DESC",
                      (slug(name),)).fetchone()
        c.close()
        if not r:
            return {"error": "not found: " + slug(name)}
        body = r["body"] or ""
        if note.strip():
            today = datetime.now().astimezone().strftime("%Y-%m-%d")
            body = body.rstrip() + "\n\n## Status " + status.upper() + " on " + today + \
                "\n" + note.strip() + "\n"
        return self.save(r["name"], r["description"] or "", body, r["type"] or "project",
                         r["project"] or "general", status)

    # -- read -------------------------------------------------------------

    def get(self, name):
        name = slug(name)
        c = self.connect()
        r = c.execute("SELECT * FROM memories WHERE name=? ORDER BY modified DESC",
                      (name,)).fetchone()
        if not r:
            like = c.execute("SELECT DISTINCT name FROM memories WHERE name LIKE ? LIMIT 8",
                             ("%" + name + "%",)).fetchall()
            c.close()
            return {"error": "not found: " + name, "similar_names": [x["name"] for x in like]}
        out = dict(r)
        out["links_to"] = sorted({x["target"] for x in c.execute(
            "SELECT target FROM links WHERE source=?", (name,))})
        out["linked_from"] = sorted({x["source"] for x in c.execute(
            "SELECT source FROM links WHERE target=?", (name,))})
        out["similar"] = [x["a"] if x["b"] == name else x["b"] for x in c.execute(
            "SELECT a, b FROM suggestions WHERE a=? OR b=? ORDER BY sim DESC", (name, name))]
        c.close()
        return out

    def pending(self, project=""):
        c = self.connect()
        rows = c.execute("SELECT DISTINCT name, project, description, modified FROM memories "
                         "WHERE status='pending' AND project LIKE ? "
                         "ORDER BY project, modified DESC", ("%" + project + "%",)).fetchall()
        c.close()
        return [dict(r) for r in rows]

    def list(self, project=""):
        c = self.connect()
        if project:
            rows = c.execute("SELECT name, description, modified, status FROM memories "
                             "WHERE project LIKE ? ORDER BY modified DESC",
                             ("%" + project + "%",)).fetchall()
        else:
            rows = c.execute("SELECT project, COUNT(*) AS n FROM memories GROUP BY project "
                             "ORDER BY n DESC").fetchall()
        c.close()
        return [dict(r) for r in rows]

    def pinned_text(self):
        """The pinned memory goes on top of EVERY hook injection, whether or not
        search picks it. Meant for a routing map ("nickname -> repo, server,
        database"): a question is about a task, and a repo path never looks
        like the task by meaning, so search alone would miss it."""
        if not self.cfg.pinned:
            return ""
        c = self.connect()
        r = c.execute("SELECT body FROM memories WHERE name=?",
                      (slug(self.cfg.pinned),)).fetchone()
        c.close()
        if not r:
            return ""
        # Only the short block goes in every message; the detail below the
        # marker stays searchable but would be dead weight here.
        return re.split(r"<!--\s*(?:END-PINNED|FIM-MAPA-CURTO)\s*-->", r["body"])[0].strip()

    def graph(self):
        c = self.connect()
        mems = c.execute("SELECT name, project, type, description, modified, status "
                         "FROM memories").fetchall()
        valid = {m["name"] for m in mems}
        links = [(r["source"], r["target"]) for r in c.execute(
            "SELECT DISTINCT source, target FROM links WHERE resolved=1")]
        sug = [(r["a"], r["b"], r["sim"]) for r in c.execute("SELECT a, b, sim FROM suggestions")]
        c.close()
        degree = {}
        for a, b in links:
            degree[a] = degree.get(a, 0) + 1
            degree[b] = degree.get(b, 0) + 1
        seen, nodes = set(), []
        for m in mems:
            if m["name"] in seen:
                continue
            seen.add(m["name"])
            nodes.append({"id": m["name"], "project": m["project"], "type": m["type"],
                          "description": m["description"] or "",
                          "date": (m["modified"] or "")[:10],
                          "degree": degree.get(m["name"], 0), "status": m["status"]})
        return {
            "nodes": nodes,
            # written: a human claim ("this depends on that"). suggested: text similarity only.
            "edges": [{"from": a, "to": b} for a, b in links
                      if a in valid and b in valid and a != b],
            "suggestions": [{"from": a, "to": b, "sim": s} for a, b, s in sug
                            if a in valid and b in valid and a != b],
        }
