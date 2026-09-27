"""Suggest links between memories from vector similarity.

Results go to a SEPARATE table (`suggestions`), never to `links`: search
expansion only follows hand-written edges, which carry relationships the
vectors cannot see. Mixing both would make the search repeat what its vector
half already did. Markdown files are never touched. Re-running is idempotent.
"""
import numpy as np

MAX_PER_MEMORY = 4   # keeps a single node from turning into a hairball
ORPHAN_FLOOR = 0.25  # below this an orphan stays an orphan: don't invent kinship


def family(name):
    """First two parts of the slug: `project-notes-foo` and `project-notes-bar`
    belong to the same family."""
    return "-".join(name.split("-")[:2])


def suggest_links(store, threshold=0.60, log=print):
    c = store.connect()
    names = {r["id"]: r["name"] for r in c.execute("SELECT id, name FROM memories")}
    by_mem = {}
    for r in c.execute("SELECT ch.memory_id m, v.v v FROM chunks ch "
                       "JOIN vectors v ON v.chunk_id = ch.id"):
        by_mem.setdefault(r["m"], []).append(np.frombuffer(r["v"], dtype="float32"))
    c.execute("DELETE FROM suggestions")
    if len(by_mem) < 2:
        c.commit()
        c.close()
        return {"suggestions": 0}

    ids = sorted(by_mem)
    # memory vector = mean of its chunk vectors, re-normalised
    M = np.vstack([np.mean(by_mem[i], axis=0) for i in ids])
    M /= np.linalg.norm(M, axis=1, keepdims=True) + 1e-9
    # CENTERING: subtract the mean vector before comparing. Otherwise what
    # dominates is what ALL memories share (same language, same technical tone,
    # identical boilerplate headers), and near-identical templates score 0.9+
    # against each other. Centered, what is left is what tells them apart.
    M = M - M.mean(axis=0)
    M /= np.linalg.norm(M, axis=1, keepdims=True) + 1e-9
    S = M @ M.T
    np.fill_diagonal(S, -1.0)

    tri = S[np.triu_indices(len(ids), 1)]
    log("similarity (centered): p50=%.3f p90=%.3f p99=%.3f max=%.3f" % (
        np.percentile(tri, 50), np.percentile(tri, 90), np.percentile(tri, 99), tri.max()))

    written = {tuple(sorted((r["source"], r["target"]))) for r in
               c.execute("SELECT source, target FROM links WHERE resolved=1")}
    cand = {}

    def put(pair, s):
        cand[pair] = max(cand.get(pair, 0.0), float(s))

    # 1) each memory's closest neighbours above the threshold
    for i in range(len(ids)):
        a, in_family = names[ids[i]], 0
        for j in np.argsort(-S[i])[:MAX_PER_MEMORY]:
            if S[i][j] < threshold:
                break
            b = names[ids[j]]
            if a == b:
                continue
            # without a cap, a family of templated memories closes into a
            # tight ball of edges that carry no information
            if family(a) == family(b):
                if in_family >= 2:
                    continue
                in_family += 1
            pair = tuple(sorted((a, b)))
            if pair not in written:
                put(pair, S[i][j])

    # 2) every ORPHAN gets at least its nearest neighbour, even below the
    #    threshold. A memory 0.003 short of the threshold stayed loose; lowering
    #    the global threshold to fix that fills the graph with noise.
    linked = {n for pair in written | set(cand) for n in pair}
    for i in range(len(ids)):
        a = names[ids[i]]
        if a in linked:
            continue
        for j in np.argsort(-S[i]):
            # skip the namesake in another project: it scores 1.0 and the
            # memory would be suggested to itself
            if names[ids[j]] == a:
                continue
            if S[i][j] >= ORPHAN_FLOOR:
                put(tuple(sorted((a, names[ids[j]]))), S[i][j])
            break

    c.executemany("INSERT INTO suggestions VALUES(?,?,?)",
                  [(a, b, round(s, 4)) for (a, b), s in cand.items()])
    c.commit()
    c.close()
    return {"suggestions": len(cand), "threshold": threshold}
