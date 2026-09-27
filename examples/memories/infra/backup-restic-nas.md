---
name: backup-restic-nas
description: "Nightly restic backups to nas-1: schedule, retention, and how to restore a single file."
metadata:
  type: reference
  modified: 2026-01-20T08:00:00Z
---

## Schedule

Systemd timer `restic-backup.timer` on every server, 02:00, retention
`--keep-daily 7 --keep-weekly 4 --keep-monthly 6`.

## Restore one file

```bash
restic -r sftp:nas-1:/srv/restic restore latest --target /tmp/r --include /etc/nginx/nginx.conf
```

Disk usage history: [[nas-disk-full-march]].
