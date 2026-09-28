"""Command line: `hippocampus init | serve | autostart | sync | suggest-links | stats | token`."""
import argparse
import json
import secrets
import sys

from . import __version__
from .config import Config


def init():
    """Prepare a local install: data folder and a random token, in ~/.hippocampus."""
    cfg = Config.from_env()
    cfg.memory_dir.mkdir(parents=True, exist_ok=True)
    if cfg.token:
        print("token: already set")
    else:
        cfg.token_file.parent.mkdir(parents=True, exist_ok=True)
        cfg.token_file.write_text(secrets.token_urlsafe(32) + "\n", encoding="utf-8")
        try:
            cfg.token_file.chmod(0o600)
        except OSError:
            pass
        print("token: created in", cfg.token_file)
    print("memories:", cfg.memory_dir)
    print("\nNext steps:\n"
          "  hippocampus autostart        # run the server now and at every login\n"
          "  python clients/claude-code/install.py --url http://127.0.0.1:%d\n"
          "Web UI: http://127.0.0.1:%d  (paste the token from %s)"
          % (cfg.port, cfg.port, cfg.token_file))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="hippocampus",
                                 description="Self-hosted long-term memory for Claude.")
    ap.add_argument("--version", action="version", version="hippocampus " + __version__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init", help="prepare a local install (data folder + token)")
    p = sub.add_parser("serve", help="run the MCP server, REST API and web UI")
    p.add_argument("--log-file", help="append output to this file (used by autostart)")
    p = sub.add_parser("autostart", help="start the server now and at every login")
    p.add_argument("--remove", action="store_true", help="stop starting it at login")
    p = sub.add_parser("sync", help="index new or changed Markdown files")
    p.add_argument("--full", action="store_true", help="rebuild the whole index from scratch")
    p = sub.add_parser("suggest-links", help="compute suggested links from vector similarity")
    p.add_argument("--threshold", type=float, default=0.60)
    sub.add_parser("stats", help="print index statistics")
    sub.add_parser("token", help="print a new random access token")
    args = ap.parse_args(argv)

    if args.cmd == "token":
        print(secrets.token_urlsafe(32))
        return
    if args.cmd == "init":
        return init()
    if args.cmd == "autostart":
        from . import autostart
        if args.remove:
            print("removed:", autostart.disable())
            if sys.platform == "win32":
                print("A server that is already running keeps running until you log out.")
            return
        if not Config.from_env().token:
            sys.exit("No token yet: run `hippocampus init` first.")
        print("enabled:", autostart.enable())
        print("log:", autostart.LOG)
        return

    cfg = Config.from_env()
    if args.cmd == "serve":
        if args.log_file:
            # no console when started at login (pythonw): everything goes to the file
            sys.stdout = sys.stderr = open(args.log_file, "a", encoding="utf-8", buffering=1)
        import uvicorn

        from .server import create_app
        from .store import Store
        store = Store(cfg)
        # pick up files added or edited while the server was down
        store.sync()
        app = create_app(cfg, store)
        uvicorn.run(app, host=cfg.host, port=cfg.port, proxy_headers=True,
                    forwarded_allow_ips="127.0.0.1")
        return

    from .store import Store
    store = Store(cfg)
    if args.cmd == "sync":
        print(json.dumps(store.sync(full=args.full), indent=1))
    elif args.cmd == "suggest-links":
        from .links import suggest_links
        print(json.dumps(suggest_links(store, args.threshold), indent=1))
    elif args.cmd == "stats":
        print(json.dumps(store.stats(), indent=1))


if __name__ == "__main__":
    sys.exit(main())
