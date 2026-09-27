---
name: shop-api-db-access
description: "How to query the shop Postgres: run a script on api-1 with the project's venv, never connect from the laptop."
metadata:
  type: reference
  modified: 2026-02-05T14:00:00Z
---

The database only accepts connections from `api-1`. The approved way is to copy
a small script there and run it with the project's venv, which already reads
the credentials from `/srv/shop-api/.env`:

```bash
scp q.py deploy@api-1:/tmp/ && ssh deploy@api-1 "/srv/shop-api/.venv/bin/python /tmp/q.py"
```

Main tables: `orders`, `order_items`, `customers`, `payments`.
Deploying changes: [[shop-api-deploy]].
