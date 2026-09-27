#!/usr/bin/env python3
"""Connect Claude Code to a Hippocampus server.

    python install.py --url https://memory.example.com --token <TOKEN>

What it does (idempotent, safe to re-run):
  1. writes ~/.hippocampus/client.json and copies the hooks to ~/.hippocampus/hooks
  2. registers the hooks in ~/.claude/settings.json (a backup is kept next to it)
  3. registers the MCP server with `claude mcp add` (user scope)

Use --uninstall to remove the hooks and the MCP server again.
"""
import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
HOME = Path.home() / ".hippocampus"
HOOKS_DIR = HOME / "hooks"
SETTINGS = Path.home() / ".claude" / "settings.json"
MARK = "hippocampus"  # every command we add contains this, which makes removal exact
FILES = ("_client.py", "recall.py", "sync.py", "extract.py")


def hook_cmd(script, *args):
    return " ".join(['"%s"' % sys.executable, '"%s"' % (HOOKS_DIR / script)] + list(args))


def wanted_hooks(extract):
    h = {
        "UserPromptSubmit": [hook_cmd("recall.py")],
        "Stop": [hook_cmd("sync.py", "--check")],
        "SessionEnd": [hook_cmd("sync.py", "--check")],
    }
    if extract:
        h["SessionEnd"].append(hook_cmd("extract.py", "--hook"))
        h["PreCompact"] = [hook_cmd("extract.py", "--hook")]
    return h


def load_settings():
    if not SETTINGS.exists():
        return {}
    return json.loads(SETTINGS.read_text(encoding="utf-8"))


def save_settings(data):
    SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    if SETTINGS.exists():
        backup = SETTINGS.with_name("settings.json.bak-%d" % int(time.time()))
        shutil.copy2(SETTINGS, backup)
        print("  backup of settings.json:", backup)
    SETTINGS.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def strip_ours(settings):
    """Remove every hook command we added before, leaving the user's own untouched."""
    hooks = settings.get("hooks", {})
    for event in list(hooks):
        groups = []
        for g in hooks[event]:
            g = dict(g, hooks=[h for h in g.get("hooks", []) if MARK not in h.get("command", "")])
            if g["hooks"]:
                groups.append(g)
        if groups:
            hooks[event] = groups
        else:
            del hooks[event]
    if not hooks:
        settings.pop("hooks", None)
    return settings


def claude(*args):
    exe = shutil.which("claude")
    if not exe:
        return None
    cmd = [exe] + list(args)
    if exe.lower().endswith((".cmd", ".bat")):
        cmd = ["cmd", "/c"] + cmd
    return subprocess.run(cmd, capture_output=True, text=True)


def install(a):
    url = a.url.rstrip("/")
    print("1/3 client config and hooks ->", HOME)
    HOOKS_DIR.mkdir(parents=True, exist_ok=True)
    for f in FILES:
        shutil.copy2(HERE / f, HOOKS_DIR / f)
    cfg_file = HOME / "client.json"
    cfg = json.loads(cfg_file.read_text(encoding="utf-8")) if cfg_file.exists() else {}
    cfg.update({"url": url, "token": a.token, "server_name": a.name})
    if a.owner:
        cfg["owner"] = a.owner
    cfg.setdefault("extract", {})["enabled"] = not a.no_extract
    cfg_file.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    try:
        cfg_file.chmod(0o600)
    except OSError:
        pass

    print("2/3 hooks ->", SETTINGS)
    settings = strip_ours(load_settings())
    hooks = settings.setdefault("hooks", {})
    for event, cmds in wanted_hooks(not a.no_extract).items():
        hooks.setdefault(event, []).append(
            {"hooks": [{"type": "command", "command": c, "timeout": 10} for c in cmds]})
    save_settings(settings)

    print("3/3 MCP server '%s' -> %s/mcp" % (a.name, url))
    claude("mcp", "remove", "--scope", "user", a.name)
    r = claude("mcp", "add", "--transport", "http", "--scope", "user", a.name, url + "/mcp",
               "--header", "Authorization: Bearer " + a.token)
    if r is None or r.returncode != 0:
        print("  could not run `claude mcp add`; run it yourself:")
        print('  claude mcp add --transport http --scope user %s %s/mcp '
              '--header "Authorization: Bearer <TOKEN>"' % (a.name, url))
    print("\nDone. Open a new Claude Code session; memories will be recalled automatically.")


def uninstall(a):
    save_settings(strip_ours(load_settings()))
    claude("mcp", "remove", "--scope", "user", a.name)
    print("Hooks and MCP server removed. ~/.hippocampus was kept (delete it by hand if you want).")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--url", help="server base URL, e.g. https://memory.example.com")
    ap.add_argument("--token", help="access token (HIPPOCAMPUS_TOKEN on the server)")
    ap.add_argument("--name", default="hippocampus", help="MCP server name (default: hippocampus)")
    ap.add_argument("--owner", help="your name, used in the extraction prompt")
    ap.add_argument("--no-extract", action="store_true",
                    help="skip automatic extraction at the end of sessions (uses `claude -p`)")
    ap.add_argument("--uninstall", action="store_true")
    a = ap.parse_args()
    if a.uninstall:
        return uninstall(a)
    if not a.url or not a.token:
        ap.error("--url and --token are required")
    install(a)


if __name__ == "__main__":
    main()
