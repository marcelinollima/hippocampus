---
name: nas-disk-full-march
description: "nas-1 hit 98% disk in March: old restic snapshots were never pruned. Fixed by adding prune to the timer."
metadata:
  type: project
  modified: 2026-03-20T10:00:00Z
  status: resolved
  status_at: 2026-03-21T09:00:00Z
---

## What happened

`restic forget` ran nightly but `restic prune` did not, so forgotten snapshots
still used space. Found while checking [[backup-restic-nas]].

## Status RESOLVED on 2026-03-21

Added `restic prune` weekly (Sunday 04:00). Disk back to 41%.
