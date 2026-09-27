#!/usr/bin/env python3
"""Stop / SessionEnd hook: upload memories that local sessions created or edited.

Two modes:

  --check  (what the hook calls) reads the manifest, compares mtime+size and
           exits in ~20 ms. If something changed it launches `--run` in a
           DETACHED process and returns at once: uploading takes seconds and
           must not hold the prompt.

  --run    does the work: POSTs the changed files to /api/import, which
           writes and indexes them on the server.

Fails silently. If the server is unreachable the manifest is NOT updated, so
the next attempt resends whatever is still pending.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

import _client

MANIFEST = _client.HOME / "sync-manifest.json"
BATCH = 40


def server_project(cfg, local_slug):
    """Claude Code names project folders after the absolute path (`C--Work-foo`).
    Map them to a clean project name so the same project isn't split in two."""
    if local_slug in cfg["project_map"]:
        return cfg["project_map"][local_slug]
    return re.sub(r"^[A-Za-z]--", "", local_slug)


def inventory(cfg):
    """{server path: (mtime, size, local path)}"""
    items = {}

    def add(folder, project):
        for f in folder.glob("*.md"):
            if f.name in ("MEMORY.md", "README.md"):
                continue
            st = f.stat()
            items[project + "/" + f.name] = (int(st.st_mtime), st.st_size, str(f))

    for root in cfg["sync_roots"]:
        root = Path(root).expanduser()
        if root.is_dir():
            for proj in root.iterdir():
                if (proj / "memory").is_dir():
                    add(proj / "memory", server_project(cfg, proj.name))
    for extra in cfg["extra_dirs"]:
        folder = Path(extra["path"]).expanduser()
        if folder.is_dir():
            add(folder, extra["project"])
    return items


def changed(cfg):
    try:
        old = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        old = {}
    now = inventory(cfg)
    diff = {k: v for k, v in now.items() if old.get(k, [None, None])[:2] != [v[0], v[1]]}
    return now, diff


def check():
    cfg = _client.load()
    if not cfg["url"] or not cfg["token"]:
        return
    _, diff = changed(cfg)
    if diff:
        subprocess.Popen([sys.executable, __file__, "--run"], stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         creationflags=_client.detached_flags(), close_fds=True)


def run():
    cfg = _client.load()
    now, diff = changed(cfg)
    if not diff:
        return
    _client.log("sync", "%d changed file(s)" % len(diff))
    items = sorted(diff.items())
    for i in range(0, len(items), BATCH):
        files = [{"path": dest, "content": Path(local).read_text(encoding="utf-8",
                                                                  errors="replace")}
                 for dest, (_, _, local) in items[i:i + BATCH]]
        try:
            res = _client.post(cfg, "/api/import", {"files": files}, 900)
        except Exception as e:
            _client.log("sync", "FAILED: %s" % e)
            return
        _client.log("sync", "server: %s" % json.dumps(res.get("sync", res))[:200])
    # only record the manifest when EVERYTHING worked: failures retry next time
    MANIFEST.parent.mkdir(exist_ok=True)
    MANIFEST.write_text(json.dumps({k: [v[0], v[1]] for k, v in now.items()}), encoding="utf-8")
    _client.log("sync", "ok, manifest updated")


if __name__ == "__main__":
    try:
        run() if "--run" in sys.argv else check()
    except Exception as e:
        _client.log("sync", "error: %s: %s" % (type(e).__name__, e))
