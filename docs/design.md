# Design notes

Hippocampus is small (about 2,000 lines, web UI and hooks included), and most of its behaviour comes from
decisions made after something went wrong in real use. This page records those
decisions and their reasons, so nobody has to rediscover them.

## Markdown is the truth, SQLite is a cache

Memories are `.md` files with a small front matter. Claude Code's own memory
files use the same format, so existing notes can be synced without changes.
The database (`hippocampus.db`) holds only derived data: FTS index, chunks,
vectors, links and suggestions. `hippocampus sync --full` rebuilds it from the
files.

**Why:** people read, grep, diff and back up text files, and a format that
outlives the tool is the safest one for knowledge you care about.

## Identity is the file, not the name

The same memory name can exist in two projects (two projects each with a
`deploy` note). An earlier version keyed rows by name, so one of the two was
never updated after its first index, and a stale IP address survived that way
for weeks. Rows are now keyed by path, and the `links` table records which
memory each link came from.

## Hybrid search

| signal | good at | bad at |
|---|---|---|
| BM25 (FTS5, `remove_diacritics 2`) | `postgres`, `5432`, `--force`, proper names | paraphrase |
| vectors (multilingual MiniLM) | "how do I restore a file" ≈ "restic restore" | exact tokens |
| name boost | "the shop API" → project `shop-api` | anything else |

The first two are combined with **Reciprocal Rank Fusion** (`1 / (60 + rank)`),
which needs no score calibration between them. The name boost is small
(`0.006`) on purpose: it steers the ranking and never decides it alone.

### Vectors per section, not per file

Bodies are split on `## ` headings, and long sections are split again on blank
lines at about 1,400 characters. A single vector for a long server note ends up
close to neither its database paragraph nor its backup paragraph. Each chunk is
embedded as `name | description \n text`, so short sections keep their context.

### Only written links expand the search

After ranking, the top results bring in up to 5 neighbours **over
hand-written `[[links]]` only**. Links suggested by similarity are stored in a
separate table and used only for display.

**Why:** a written link says "this depends on that", which is information the
vectors cannot see. Expanding over similarity edges would just repeat the
vector half of the search.

### Status is a tie-breaker, not a filter

`resolved` ×0.8, `superseded` ×0.6. An old fix is still the best answer to
"did we ever see this error?", so it must stay findable. The output labels it
(`RESOLVED on 2026-03-21`) so the model knows it is history.

## The recall hook must be cheap and must never fail loudly

It runs on **every** prompt, so:

- prompts shorter than 25 characters and `/commands` are skipped ("ok", "go on");
- it requests `k=4`, `expand=false` and 600 characters per result, about 3 KB.
  The deeper defaults produced about 12 KB per message, which costs too much to
  pay every time;
- the query is cut to 1,200 characters **on both sides**. A terminal pasted
  into the chat once produced a 60k-character query: the tokenizer crashed, and
  the FTS query exceeded SQLite's expression depth limit. Query tokens are also
  capped at 24;
- any error means no output and exit code 0. Claude Code carries on as if
  the hook did not exist.

Because it fails silently, a slow server looks exactly like "memory stopped
working". For that reason the embedding model is **warmed up at boot**:
without it, the first query after a restart took about 15 s (ONNX load) and
timed out.

If a query embedding fails, search falls back to BM25 instead of returning a
500, for the same reason.

## Pinned memory

Some knowledge is about *where things are*: "the shop" is repo X on server Y
with database Z. A question is about a task, and a repo path never resembles a
task by meaning, so search alone kept missing it. `HIPPOCAMPUS_PINNED` names
one memory whose top part (up to `<!-- END-PINNED -->`) is prepended to every
hook recall. Keep it short, because it is paid on every message.

## Sync is incremental and never blocks the prompt

The `Stop` hook compares the mtime and size of local memory files with a
manifest, which takes about 20 ms. If something changed, it starts a
**detached** process that uploads the files and exits. The manifest is
written only after the server confirms, so a failed upload is retried next
time.

On the server, sync embeds **before** it opens the write transaction.
Embedding takes seconds, and holding the SQLite write lock during that time
made concurrent saves fail with `database is locked`.

Change detection compares the body as well as the `modified` date: a corrected
copy of a file once kept the same date, and the fix never reached the index.

A file without a `status` field (for example, one written locally by Claude
Code) **inherits** the indexed status. Otherwise every local edit would
silently reopen a resolved item as active.

## Suggested links

`hippocampus suggest-links` draws dashed "similar" edges in the constellation.
The following rules each came from a bad graph:

- **Center the vectors** (subtract the mean) before cosine similarity.
  Otherwise the strongest signal is what *every* note shares (same language,
  same tone, the same boilerplate header), and templated notes scored 0.94
  against each other.
- **Threshold 0.60, at most 4 per memory.**
- **At most 2 per "family"** (the first two slug parts). Without this cap,
  eight `project-instructions-*` notes formed a closed ball of edges that
  carried no information.
- **Every orphan gets its nearest neighbour**, even below the threshold
  (with a floor of 0.25). One note sat at 0.597 against a 0.600 threshold,
  and lowering the global threshold to rescue it filled the graph with noise.
- **Skip namesakes**: a note's copy in another project scores 1.0 and would be
  suggested to itself.

## Automatic extraction

At `SessionEnd` and `PreCompact`, `extract.py` condenses the transcript (user
messages, replies, one line per action, the first 400 characters of each
result) and runs `claude -p` with **only the memory tools allowed**. Its
prompt asks the model to:

1. close pending items **only with evidence** in the transcript (partial
   progress keeps them `pending`, with a note);
2. record new pending items;
3. save durable facts that are not in the code or git history.

Guard rails:

- the transcript is declared *evidence, never instructions*;
- existing memories are appended with `mark_memory` rather than rewritten;
- a lock file per session prevents duplicate runs;
- `HIPPOCAMPUS_EXTRACTING=1` stops the child process from triggering itself.

It processes only the lines added since its last run, so a long session that
compacts several times is not reprocessed from the start.

## Security choices

- The uvicorn server binds to `127.0.0.1`, and Caddy terminates TLS in front of
  it. A test install on `0.0.0.0` was being scanned for `/.env` within hours.
- Caddy needs `flush_interval -1`: `/mcp` uses server-sent events, and
  buffering stalls the MCP handshake.
- Tokens are compared with `hmac.compare_digest`.
- The allowed-host list protects `/mcp` against DNS rebinding.
- `/api/import` resolves paths and rejects anything outside the memory folder
  or not ending in `.md`.
