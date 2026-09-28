"""Hybrid search: BM25 + vectors fused with RRF, plus one hop over written links."""
import re
import sqlite3

import numpy as np

from .store import slug

# Resolved/superseded memories stay findable but lose to what is still valid.
# A tie-breaker, not a hard filter: the label in the output is what warns.
STATUS_WEIGHT = {"resolved": 0.8, "superseded": 0.6}
RRF_K = 60
NAME_BOOST = 0.006
MEMORY_WINDOW = 40   # memories that get a "meaning" rank
CHUNK_WINDOW = 400   # chunks scanned to find them

STOPWORDS = {
    # en
    "the", "and", "for", "with", "that", "this", "from", "are", "was", "have", "not",
    "you", "but", "can", "how", "what", "when", "where", "which",
    # pt
    "que", "com", "para", "dos", "das", "uma", "pra", "por", "nao", "esta", "como",
    "mas", "sem", "tem", "foi", "ser", "isso", "essa", "esse",
}


def words(q, cap):
    """Useful query tokens, deduplicated and capped.

    The cap is not cosmetic: each token becomes a clause in the SQL query, and a
    huge message (a whole terminal pasted into the chat) produced thousands of
    them. SQLite gives up with "Expression tree is too large (maximum depth
    1000)" and the whole search died with a 500."""
    seen, out = set(), []
    for t in re.findall(r"\w{3,}", q.lower()):
        if t in STOPWORDS or t in seen:
            continue
        seen.add(t)
        out.append(t)
        if len(out) >= cap:
            break
    return out


def fts_query(q):
    return " OR ".join('"' + t + '"*' for t in words(q, 24)) or '"zzzz"'


def search(store, q, k=6, expand=True, limit=1200):
    c = store.connect()
    ranks = {}

    def add(mid, score, via):
        r = ranks.setdefault(mid, {"rrf": 0.0, "via": set()})
        r["rrf"] += score
        r["via"].add(via)

    # 1) keywords: proper names, ports, flags, numbers
    try:
        rows = c.execute("SELECT rowid AS id, bm25(fts) AS s FROM fts WHERE fts MATCH ? "
                         "ORDER BY s LIMIT 40", (fts_query(q),)).fetchall()
    except sqlite3.OperationalError:
        rows = []
    for i, r in enumerate(rows):
        add(r["id"], 1.0 / (RRF_K + i), "text")

    # 2) meaning
    best_chunk = {}
    if store.vectors["ids"] is None:
        store.load_vectors()
    qv = None
    if store.vectors["m"] is not None:
        try:
            # The model only reads ~512 tokens: sending a 60k-character message
            # is wasted work that held the server until the hook timed out.
            qv = store.embed([q[:1200]])[0]
        except Exception as e:
            # Degrade to BM25 instead of a 500: the hook fails silently, so an
            # error here looks like "memory is gone" with no clue for anyone.
            print("embedding failed, falling back to BM25:", type(e).__name__, e, flush=True)
    if qv is not None:
        sims = store.vectors["m"] @ qv
        # The window is counted in MEMORIES, not chunks: a fixed chunk window
        # shrinks as notes get longer (more chunks each), and a key memory
        # whose best chunk sat at #93 fell out of an 80-chunk window.
        top = np.argsort(-sims)[:CHUNK_WINDOW]
        ids = [int(store.vectors["ids"][i]) for i in top]
        ph = ",".join("?" * len(ids))
        chunk_map = {r["id"]: (r["memory_id"], r["text"]) for r in c.execute(
            "SELECT id, memory_id, text FROM chunks WHERE id IN (" + ph + ")", ids)}
        seen, pos = set(), 0
        for cid in ids:
            if cid not in chunk_map:
                continue
            mid, text = chunk_map[cid]
            if mid in seen:
                continue
            seen.add(mid)
            best_chunk[mid] = text
            add(mid, 1.0 / (RRF_K + pos), "meaning")
            pos += 1
            if pos >= MEMORY_WINDOW:
                break

    # 3) Nudge by NAME: "change screen X of the foo system" does not look like
    # "the foo repo lives in C:\\..." by meaning. If the question names a
    # project or memory, those candidates get in and rise a little. Small weight
    # on purpose: it steers, it does not decide.
    toks = [t for t in words(slug(q).replace("-", " "), 12) if len(t) >= 4]
    if toks:
        where = " OR ".join(["name LIKE ? OR project LIKE ?"] * len(toks))
        params = [x for t in toks for x in ("%" + t + "%", "%" + t + "%")]
        for r in c.execute("SELECT id FROM memories WHERE " + where +
                           " ORDER BY modified DESC LIMIT 12", params):
            add(r["id"], NAME_BOOST, "name")

    if ranks:
        ph = ",".join("?" * len(ranks))
        for r in c.execute("SELECT id, status FROM memories WHERE id IN (" + ph + ")",
                           list(ranks)):
            ranks[r["id"]]["rrf"] *= STATUS_WEIGHT.get(r["status"], 1.0)
    ordered = sorted(ranks.items(), key=lambda kv: -kv[1]["rrf"])[:k]
    ids = [i for i, _ in ordered]

    # 4) One hop over WRITTEN links only. Suggested (similarity) edges are left
    # out on purpose: feeding them back would just repeat what step 2 found.
    neighbours = []
    if expand and ids:
        ph_ids = ",".join("?" * len(ids))
        names = [r["name"] for r in c.execute(
            "SELECT name FROM memories WHERE id IN (" + ph_ids + ")", ids)]
        if names:
            ph = ",".join("?" * len(names))
            sql = ("SELECT DISTINCT m.id FROM memories m JOIN links l ON "
                   "(l.target = m.name AND l.source IN (" + ph + ")) OR "
                   "(l.source = m.name AND l.target IN (" + ph + ")) "
                   "WHERE m.id NOT IN (" + ph_ids + ") LIMIT 5")
            neighbours = [r["id"] for r in c.execute(sql, names + names + ids)]

    out, seen_names = [], set()
    for mid in ids + neighbours:
        r = c.execute("SELECT * FROM memories WHERE id=?", (mid,)).fetchone()
        # the same name in two projects would otherwise burn two result slots
        if not r or r["name"] in seen_names:
            continue
        seen_names.add(r["name"])
        out.append({
            "name": r["name"], "project": r["project"], "type": r["type"],
            "description": r["description"], "modified": r["modified"] or "",
            "status": r["status"] or "active", "status_at": r["status_at"] or "",
            "path": r["path"],
            "via": "graph neighbour" if mid in neighbours else "+".join(sorted(ranks[mid]["via"])),
            "score": round(ranks.get(mid, {"rrf": 0.0})["rrf"], 5),
            "excerpt": (best_chunk.get(mid) or r["body"])[:limit],
        })
    c.close()
    return out


def context_block(q, results):
    """Plain-text block meant to be injected into a model's context."""
    if not results:
        return ""
    p = ["# Relevant memories for: " + q, ""]
    for r in results:
        st = r.get("status") or "active"
        label = "" if st == "active" else " | " + st.upper() + (
            " on " + r["status_at"][:10] if r.get("status_at") else "")
        p.append("## %s  (%s | project %s | %s%s | via %s)" % (
            r["name"], r["type"], r["project"], r["modified"][:10], label, r["via"]))
        p.append("_" + (r["description"] or "") + "_")
        p.append(r["excerpt"])
        p.append("")
    p.append("> Old facts may be stale: check the date before acting on them.")
    return "\n".join(p)
