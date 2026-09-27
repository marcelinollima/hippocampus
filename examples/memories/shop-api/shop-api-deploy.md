---
name: shop-api-deploy
description: "How to deploy the shop API: build, copy, restart, check. Always run the syntax check first."
metadata:
  type: reference
  modified: 2026-02-03T09:30:00Z
---

## Steps

1. `python -m compileall src` locally. A single SyntaxError takes down **every**
   route, because the API is one process.
2. `rsync -a src/ deploy@api-1:/srv/shop-api/src/`
3. `ssh deploy@api-1 sudo systemctl restart shop-api`
4. `curl -fsS https://api.example.com/health` must answer `ok`.

## Why the check matters

On 2026-01-28 a missing parenthesis in one admin route took the whole API down
for 12 minutes. Related: [[shop-api-db-access]].
