# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- Daily review on the server: `review.py --auto` plus a systemd service and
  timer (`deploy/systemd/hippocampus-review.*`) that judge with Claude Code
  under your subscription. `HIPPOCAMPUS_REVIEW` = `off` (default) | `report` |
  `apply`.
- Verdicts are stored (`/api/review/record`), and `--changed` reviews only
  items that changed or got newer evidence since their last review.
- In `report` mode, `list_pending` shows "looks done" with the quote under the
  item, until the memory changes.
- The client reads `HIPPOCAMPUS_LANG` and `HIPPOCAMPUS_OWNER` from the
  environment, so it can run on the server with the server's `.env`.

## [0.4.0] - 2026-11-02

Pending items no longer stay open forever just because the fix was written
somewhere else. On the author's server, the first review of the backlog
closed 11 of 417 pending items, each with the sentence that proved it.

### Added
- `save_memory` and `mark_memory` answer with `related_pending`: up to 3 open
  items that look like what was just saved, with a hint to resolve them when the
  work finished them. Threshold calibrated on real memories (centered cosine 0.50).
- The extraction hook acts on `related_pending`, with the same "only with
  evidence" rule.
- `/api/review` and `clients/claude-code/review.py`: review the pending
  backlog. Each pending memory goes to `claude -p` (no tools) with the newer
  memories that look like it; the result is a report, and `--apply` marks as
  resolved only the items approved in it, each with the quote that proves it.

### Changed
- `list_pending` is paged (`limit`, default 50, and `offset`), oldest first, with
  the total, the date each item was opened and the date of its last note.
  Descriptions are cut at 160 characters. With 400+ pending items the old
  output passed 100k characters and clients refused it.

## [0.3.0] - 2026-09-29

Hippocampus now speaks English and Portuguese end to end, not only in the web UI.

### Added
- `HIPPOCAMPUS_LANG` (`en` | `pt`): default MCP instructions, tool replies and the
  context block injected into Claude in the chosen language.
- `/api/search` accepts `lang`, so each client can ask for its own language.
- Claude Code installer `--lang`: recall header and extracted memories in that language.
- Web UI: EN/PT button; the choice is remembered in the browser.

### Fixed
- Recall hook on Windows: output is UTF-8, so accents no longer arrive as "�".

### Documentation
- README: a real example of the context block Claude receives, a comparison with
  vector-only memory, screenshots of search results and of a memory's links, and a
  list of known limitations.

### Unchanged on purpose
- Tool names, statuses, types and API fields are the same in every language.

## [0.2.0] - 2026-09-28

Running on your own computer is now a first-class option, not just a trial.

### Added
- `hippocampus init`: creates `~/.hippocampus` with a data folder and a random token.
- `hippocampus autostart [--remove]`: starts the server now and at every login, with
  no admin rights (Windows Startup folder, macOS LaunchAgent, systemd user unit).
- `hippocampus serve --log-file`, used by autostart since there is no terminal.
- `docker-compose.local.yml`: Docker on your own machine, without Caddy or a domain.
- The Claude Code installer reads the local token when `--token` is omitted.
- CI runs the whole local install on Windows and macOS.

### Changed
- Default data folder is `~/.hippocampus/data` instead of `./data`, and the token
  is read from `~/.hippocampus/server-token` when `HIPPOCAMPUS_TOKEN` is not set.
  Installs that set `HIPPOCAMPUS_DATA_DIR` (Docker, systemd) are not affected.

## [0.1.1] - 2026-09-28

Fixes found while migrating a real 361-memory installation.

### Fixed
- Search: the vector window is now sized in memories (40) instead of chunks (80).
  With long notes split into many chunks, a key memory could fall out of the
  window and lose its "meaning" rank.
- Import: a file synced under a different name for the same memory
  (`db_access.md` vs `db-access.md`) now overwrites the existing file instead
  of creating a duplicate.
- Web UI: zooms to fit the constellation once the layout settles, and a weak
  centering force keeps unlinked memories on screen. `?lang=en|pt` overrides
  the browser language.

## [0.1.0] - 2026-09-28

First public release.

### Added
- MCP server (streamable HTTP) with `search_memory`, `read_memory`, `save_memory`,
  `mark_memory`, `list_pending`, `list_memories`.
- Hybrid search: BM25 (FTS5) + local multilingual embeddings fused with RRF, plus
  one-hop expansion over hand-written `[[links]]`.
- Memory status (`active`, `pending`, `resolved`, `superseded`) with dated notes.
- Pinned memory injected on every recall (`HIPPOCAMPUS_PINNED`).
- Constellation web UI (English and Portuguese).
- Claude Code hooks: recall on every prompt, background sync of local memory
  folders, automatic extraction at session end. Cross-platform installer.
- `/mcp/<secret>` URL for claude.ai custom connectors.
- Docker Compose + Caddy deployment, systemd unit.
