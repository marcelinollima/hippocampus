# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/) and the project uses
[Semantic Versioning](https://semver.org/).

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
