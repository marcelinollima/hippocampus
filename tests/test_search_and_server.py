from starlette.testclient import TestClient

from hippocampus.search import context_block, search
from hippocampus.server import create_app

AUTH = {"Authorization": "Bearer test-token"}


def test_keyword_search_finds_the_right_memory(store):
    res = search(store, "restic restore a single file")
    assert res[0]["name"] == "backup-restic-nas"


def test_resolved_memories_rank_below_active(store):
    res = search(store, "restic prune snapshots disk", k=7)
    names = [r["name"] for r in res]
    assert "nas-disk-full-march" in names
    assert context_block("q", res).count("RESOLVED") >= 1


def test_graph_expansion_adds_neighbours(store):
    res = search(store, "SyntaxError takes down every route", k=1, expand=True)
    assert res[0]["name"] == "shop-api-deploy"
    assert any(r["via"] == "graph neighbour" for r in res[1:])


def test_huge_query_does_not_crash(store):
    assert isinstance(search(store, "word " * 50000), list)


def client(store):
    return TestClient(create_app(store.cfg, store, warmup=False), base_url="http://localhost:8765")


def test_api_requires_token(store):
    c = client(store)
    assert c.get("/api/graph").status_code == 401
    assert c.get("/api/graph", headers={"Authorization": "Bearer nope"}).status_code == 401
    assert c.get("/api/graph", headers=AUTH).status_code == 200
    assert c.get("/health").text.startswith("ok")


def test_mcp_requires_token_or_url_secret(store):
    init = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
    hdrs = {"Accept": "application/json, text/event-stream"}
    with client(store) as c:  # the MCP transport needs the app lifespan
        assert c.post("/mcp", json=init, headers=hdrs).status_code == 401
        assert c.post("/mcp/wrong", json=init, headers=hdrs).status_code == 401
        for r in (c.post("/mcp/s3cret", json=init, headers=hdrs),
                  c.post("/mcp", json=init, headers={**hdrs, **AUTH})):
            assert r.status_code == 200
            assert "search_memory" in r.text and "mark_memory" in r.text


def test_search_endpoint_puts_pinned_on_top(store):
    r = client(store).post("/api/search", headers=AUTH,
                           json={"q": "deploy the shop api", "pinned": True, "expand": False})
    d = r.json()
    assert d["context"].startswith("# Pinned")
    assert all(x["name"] != "systems-map" for x in d["results"])


def test_import_endpoint_indexes_new_files(store):
    c = client(store)
    r = c.post("/api/import", headers=AUTH, json={"files": [
        {"path": "infra/dns.md", "content": "---\nname: dns\n---\n\nCloudflare zones."}]})
    assert r.json()["sync"]["memories"] == 8
    assert c.post("/api/import", headers=AUTH,
                  json={"files": [{"path": "../x.md", "content": ""}]}).status_code == 400
