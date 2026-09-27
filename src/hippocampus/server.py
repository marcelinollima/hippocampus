"""MCP server + REST API + the constellation web UI, in one ASGI app."""
import hmac
import json

from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.concurrency import run_in_threadpool as bg
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, PlainTextResponse

from . import __version__
from .search import context_block, search
from .store import Store


def quiet(*_):
    pass


def _same(a, b):
    return bool(a) and bool(b) and hmac.compare_digest(a.encode(), b.encode())


def create_app(cfg, store=None, warmup=True):
    if not cfg.token:
        raise SystemExit("HIPPOCAMPUS_TOKEN is not set. Generate one with `hippocampus token`.")
    store = store or Store(cfg)
    mcp = MCPServer(name="hippocampus", instructions=cfg.instructions)

    # -- MCP tools --------------------------------------------------------

    @mcp.tool(description="Search memories by meaning + keywords + link graph. Use it BEFORE "
                          "touching any server, database or system of " + cfg.owner + ".")
    def search_memory(query: str, limit: int = 6) -> str:
        res = search(store, query, max(1, min(limit, 15)))
        return context_block(query, res) or "No memory found for: " + query

    @mcp.tool(description="Read a whole memory by name, with what it links to, what links "
                          "to it and similar memories.")
    def read_memory(name: str) -> str:
        return json.dumps(store.get(name), ensure_ascii=False, indent=1)

    @mcp.tool(description="Create or update a memory. Link to others with [[other-name]] in "
                          "the body. type: project | reference | feedback | user. status: "
                          "active | pending | resolved | superseded (empty keeps the current).")
    def save_memory(name: str, description: str, body: str, type: str = "project",
                    project: str = "general", status: str = "") -> str:
        return json.dumps(store.save(name, description, body, type, project, status or None),
                          ensure_ascii=False)

    @mcp.tool(description="Change a memory's status (active | pending | resolved | "
                          "superseded) and append a dated note saying why. Use it when a "
                          "pending item gets done.")
    def mark_memory(name: str, status: str, note: str = "") -> str:
        return json.dumps(store.mark(name, status, note), ensure_ascii=False)

    @mcp.tool(description="List memories marked as pending (what is still to be done). "
                          "Optional project filter.")
    def list_pending(project: str = "") -> str:
        rows = store.pending(project)
        return "\n".join("- [%s] %s (%s): %s" % (r["project"], r["name"],
                                                (r["modified"] or "")[:10], r["description"] or "")
                         for r in rows) or "(no pending memories)"

    @mcp.tool(description="List the memories of a project; without arguments, list projects.")
    def list_memories(project: str = "") -> str:
        rows = store.list(project)
        if project:
            return "\n".join("- %s (%s): %s" % (r["name"], (r["modified"] or "")[:10],
                                                r["description"] or "") for r in rows) or "(empty)"
        return "\n".join("- %s: %d memories" % (r["project"], r["n"]) for r in rows) or "(empty)"

    # -- REST API (used by the web UI and the Claude Code hooks) ---------

    def authorized(req):
        h = req.headers.get("authorization", "")
        return _same(h[7:] if h.lower().startswith("bearer ") else "", cfg.token)

    def deny():
        return JSONResponse({"error": "unauthorized"}, 401)

    @mcp.custom_route("/", methods=["GET"])
    async def home(req: Request):
        return FileResponse(cfg.web_dir / "index.html")

    @mcp.custom_route("/health", methods=["GET"])
    async def health(req: Request):
        s = store.stats()
        return PlainTextResponse("ok v%s memories=%d links=%d" % (
            __version__, s["memories"], s["links"]))

    @mcp.custom_route("/api/graph", methods=["GET"])
    async def r_graph(req: Request):
        return JSONResponse(store.graph()) if authorized(req) else deny()

    @mcp.custom_route("/api/search", methods=["POST"])
    async def r_search(req: Request):
        if not authorized(req):
            return deny()
        d = await req.json()
        q = str(d.get("q", ""))
        # The hook sends expand=false and a short limit: it fires on every
        # message and must not eat the context window. MCP (a deliberate
        # search) uses the deeper defaults.
        res = await bg(search, store, q, int(d.get("k", 6)), bool(d.get("expand", True)),
                       int(d.get("limit", 1200)))
        pinned = store.pinned_text() if d.get("pinned") else ""
        if pinned:  # it already goes in full on top: repeating it is waste
            res = [x for x in res if x["name"] != store.cfg.pinned]
        ctx = context_block(q, res)
        if pinned:
            ctx = "# Pinned\n\n" + pinned + ("\n\n" + ctx if ctx else "")
        return JSONResponse({"results": res, "context": ctx})

    @mcp.custom_route("/api/memory", methods=["GET", "POST"])
    async def r_memory(req: Request):
        if not authorized(req):
            return deny()
        if req.method == "GET":
            return JSONResponse(store.get(req.query_params.get("name", "")))
        d = await req.json()
        return JSONResponse(await bg(store.save, d.get("name", ""), d.get("description", ""),
                                     d.get("body", ""), d.get("type", "project"),
                                     d.get("project", "general"), d.get("status") or None))

    @mcp.custom_route("/api/mark", methods=["POST"])
    async def r_mark(req: Request):
        if not authorized(req):
            return deny()
        d = await req.json()
        return JSONResponse(await bg(store.mark, d.get("name", ""), d.get("status", ""),
                                     d.get("note", "")))

    @mcp.custom_route("/api/import", methods=["POST"])
    async def r_import(req: Request):
        """Receive raw Markdown files from a client and index what changed.
        Body: {"files": [{"path": "project/name.md", "content": "..."}]}"""
        if not authorized(req):
            return deny()
        d = await req.json()
        written = [store.import_file(f.get("path", ""), f.get("content", ""))
                   for f in d.get("files", [])]
        bad = [w for w in written if w.get("error")]
        if bad:
            return JSONResponse({"error": "invalid path in batch", "results": written}, 400)
        return JSONResponse({"ok": True, "sync": await bg(store.sync, False, quiet)})

    @mcp.custom_route("/api/sync", methods=["POST"])
    async def r_sync(req: Request):
        """Re-read the Markdown folder (after editing files on the server by hand)."""
        if not authorized(req):
            return deny()
        return JSONResponse(await bg(store.sync, False, quiet))

    # -- assemble ---------------------------------------------------------

    app = mcp.streamable_http_app(
        streamable_http_path="/mcp", stateless_http=True,
        transport_security=TransportSecuritySettings(
            allowed_hosts=cfg.allowed_hosts,
            allowed_origins=[s + h for h in cfg.allowed_hosts for s in ("http://", "https://")],
        ),
    )
    app = Auth(app, cfg)

    store.load_vectors()
    if warmup:
        # Load the model at boot. Otherwise the FIRST search after a restart
        # takes ~15s (ONNX load), the hook times out and fails silently.
        store.embed(["warmup"])
    return app


class Auth:
    """Protects /mcp with the bearer token (/api routes check it themselves).

    Optionally also accepts /mcp/<URL_SECRET> without a header, for MCP
    clients that cannot send custom headers (e.g. claude.ai custom connectors).
    """

    def __init__(self, inner, cfg):
        self.inner, self.cfg = inner, cfg

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            path = scope.get("path", "").rstrip("/")
            if path.startswith("/mcp/"):
                if _same(path[5:], self.cfg.url_secret):
                    scope = dict(scope, path="/mcp", raw_path=b"/mcp")
                    return await self.inner(scope, receive, send)
                return await self._reject(send)
            if path == "/mcp":
                hdrs = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
                h = hdrs.get("authorization", "")
                if not _same(h[7:] if h.lower().startswith("bearer ") else "", self.cfg.token):
                    return await self._reject(send)
        await self.inner(scope, receive, send)

    @staticmethod
    async def _reject(send):
        await send({"type": "http.response.start", "status": 401,
                    "headers": [(b"content-type", b"text/plain")]})
        await send({"type": "http.response.body", "body": b"unauthorized"})
