"""Command line: `hippocampus serve | sync | suggest-links | stats | token`."""
import argparse
import json
import secrets
import sys

from . import __version__
from .config import Config


def main(argv=None):
    ap = argparse.ArgumentParser(prog="hippocampus",
                                 description="Self-hosted long-term memory for Claude.")
    ap.add_argument("--version", action="version", version="hippocampus " + __version__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("serve", help="run the MCP server, REST API and web UI")
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

    cfg = Config.from_env()
    if args.cmd == "serve":
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
