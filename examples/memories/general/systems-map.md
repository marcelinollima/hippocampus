---
name: systems-map
description: "Routing map: the nicknames I use -> where each system lives (repo, server, database). Pinned: goes on top of every recall."
metadata:
  type: reference
  modified: 2026-01-10T12:00:00Z
---

| nickname | code | server / database |
|---|---|---|
| "the shop", "the API" | `~/code/shop-api` (FastAPI) | `api-1` (10.0.0.12), Postgres `shop` |
| "the backups" | `~/code/infra/backup` | `nas-1`, restic repo `/srv/restic` |
| "the site" | `~/code/site` (Astro) | static, deployed by CI |

<!-- END-PINNED -->

The block above is injected into every prompt by the recall hook when
`HIPPOCAMPUS_PINNED=systems-map`. Everything below the marker stays searchable
but is not repeated on every message. See [[shop-api-deploy]] and
[[backup-restic-nas]].
