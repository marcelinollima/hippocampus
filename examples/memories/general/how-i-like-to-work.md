---
name: how-i-like-to-work
description: "Preferences: commit and push after every change; show a dry-run before any UPDATE on production data."
metadata:
  type: feedback
  modified: 2026-01-05T10:00:00Z
---

- Commit and push at the end of every set of changes, without being asked.
  **Why:** I kept forgetting and losing track of what was deployed.
- Before any `UPDATE`/`DELETE` on production, show a `SELECT` with the rows that
  would change and wait for my OK. **Why:** one wrong WHERE clause is forever.
  Applies to [[shop-api-db-access]].
