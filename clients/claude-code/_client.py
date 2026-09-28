"""Shared client settings for the Claude Code hooks (standard library only).

Settings live in ~/.hippocampus/client.json, written by install.py.
HIPPOCAMPUS_URL and HIPPOCAMPUS_TOKEN environment variables override them.
"""
import json
import os
import subprocess
import urllib.request
from datetime import datetime
from pathlib import Path

HOME = Path.home() / ".hippocampus"
CONFIG_FILE = HOME / "client.json"

DEFAULTS = {
    "url": "",
    "token": "",
    "server_name": "hippocampus",
    "owner": "the user",
    # en | pt: language of the recall header and of the memories extract writes
    "lang": "en",
    # folders shaped like <root>/<project-slug>/memory/*.md (Claude Code's own layout)
    "sync_roots": ["~/.claude/projects"],
    # other folders with memories: [{"path": "...", "project": "..."}]
    "extra_dirs": [],
    # local project slug -> project name on the server
    "project_map": {},
    "recall": {"k": 4, "min_chars": 25, "limit": 600, "timeout": 8, "pinned": True},
    "extract": {"enabled": True, "model": "sonnet", "min_chars": 3000,
                "max_chars": 150000, "timeout": 1500},
}


def load():
    cfg = json.loads(json.dumps(DEFAULTS))
    try:
        user = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        user = {}
    for k, v in user.items():
        if isinstance(v, dict) and isinstance(cfg.get(k), dict):
            cfg[k].update(v)
        else:
            cfg[k] = v
    cfg["url"] = os.environ.get("HIPPOCAMPUS_URL", cfg["url"]).rstrip("/")
    cfg["token"] = os.environ.get("HIPPOCAMPUS_TOKEN", cfg["token"])
    return cfg


def post(cfg, route, payload, timeout):
    req = urllib.request.Request(
        cfg["url"] + route, data=json.dumps(payload).encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + cfg["token"]})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def log(name, msg):
    try:
        HOME.mkdir(exist_ok=True)
        with (HOME / (name + ".log")).open("a", encoding="utf-8") as f:
            f.write(datetime.now().strftime("%Y-%m-%d %H:%M:%S ") + msg + "\n")
    except OSError:
        pass


def detached_flags():
    """Windows flags so a background child neither opens a console nor dies with the hook."""
    flags = 0
    for name in ("DETACHED_PROCESS", "CREATE_NEW_PROCESS_GROUP", "CREATE_NO_WINDOW"):
        flags |= getattr(subprocess, name, 0)
    return flags
