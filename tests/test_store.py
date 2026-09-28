from hippocampus.links import suggest_links
from hippocampus.store import chunk, normalize_status, parse_md, project_from_path, slug

quiet = lambda *_: None  # noqa: E731


def test_slug_strips_accents_and_symbols():
    assert slug("Acesso ao Banco (produção)") == "acesso-ao-banco-producao"


def test_project_from_claude_code_folder():
    assert project_from_path("C--Work-foo/memory/x.md") == "Work-foo"
    assert project_from_path("infra/x.md") == "infra"
    assert project_from_path("x.md") == "general"


def test_portuguese_status_is_accepted():
    assert normalize_status("pendente") == "pending"
    assert normalize_status("Resolvida") == "resolved"


def test_parse_md_reads_nested_metadata():
    meta, body = parse_md('---\nname: a\ndescription: "d"\nmetadata:\n  type: user\n'
                          '  status_em: 2026-01-01\n---\n\nhello')
    assert meta["name"] == "a" and meta["type"] == "user"
    assert meta["status_at"] == "2026-01-01"
    assert body == "hello"


def test_chunk_splits_on_headings_and_long_sections():
    parts = chunk("intro\n## A\n" + ("x " * 900) + "\n\n" + ("y " * 900) + "\n## B\nb")
    assert parts[0] == "intro"
    assert parts[-1] == "## B\nb"
    assert all(len(p) <= 1400 for p in parts)


def test_sync_indexes_examples(store):
    s = store.stats()
    assert s["memories"] == 7
    assert s["broken_links"] == 0
    assert s["pending"] == 1
    # second sync has nothing to do
    assert store.sync(log=quiet)["changed"] == 0


def test_sync_prunes_deleted_files(store, cfg):
    (cfg.memory_dir / "infra" / "nas-disk-full-march.md").unlink()
    r = store.sync(log=quiet)
    assert r["pruned"] == 1 and r["memories"] == 6
    # the link that pointed to it is now broken
    assert r["broken_links"] == 1


def test_save_writes_file_and_links(store, cfg):
    r = store.save("New Server", "a new box", "Uses [[backup-restic-nas]].", "reference", "infra")
    assert r["ok"] and r["path"] == "infra/new-server.md"
    assert (cfg.memory_dir / "infra" / "new-server.md").exists()
    m = store.get("new-server")
    assert m["links_to"] == ["backup-restic-nas"]
    assert "new-server" in store.get("backup-restic-nas")["linked_from"]


def test_save_keeps_existing_file_location(store, cfg):
    (cfg.memory_dir / "infra" / "memory").mkdir()
    (cfg.memory_dir / "infra" / "memory" / "old.md").write_text(
        "---\nname: old\n---\n\nbody", encoding="utf-8")
    store.sync(log=quiet)
    r = store.save("old", "", "new body", project="infra")
    assert r["path"] == "infra/memory/old.md"
    assert store.stats()["memories"] == 8


def test_mark_appends_dated_note_and_keeps_body(store):
    r = store.mark("orders-report-mismatch", "resolved", "Finance chose 'who closed'.")
    assert r["status"] == "resolved"
    m = store.get("orders-report-mismatch")
    assert "## Status RESOLVED on" in m["body"]
    assert "Cause (proved)" in m["body"]
    assert store.pending() == []


def test_save_without_status_keeps_previous(store):
    store.save("orders-report-mismatch", "d", "changed body", project="shop-api")
    assert store.get("orders-report-mismatch")["status"] == "pending"


def test_invalid_status_is_rejected(store):
    assert "error" in store.mark("systems-map", "done")


def test_import_file_rejects_path_traversal(store):
    assert "error" in store.import_file("../evil.md", "x")
    assert "error" in store.import_file("infra/x.txt", "x")
    assert store.import_file("infra/ok.md", "---\nname: ok\n---\n\nhi")["ok"]


def test_import_reuses_existing_file_for_same_memory(store, cfg):
    r = store.import_file("infra/backup_restic_nas.md",
                          "---\nname: backup_restic_nas\n---\n\nnew text")
    assert r["path"] == "infra/backup-restic-nas.md"
    assert not (cfg.memory_dir / "infra" / "backup_restic_nas.md").exists()
    store.sync(log=quiet)
    assert store.stats()["memories"] == 7
    assert "new text" in store.get("backup-restic-nas")["body"]


def test_pinned_text_stops_at_marker(store):
    t = store.pinned_text()
    assert "the shop" in t and "END-PINNED" not in t and "searchable" not in t


def test_graph_shape(store):
    g = store.graph()
    assert len(g["nodes"]) == 7
    assert {"from": "shop-api-deploy", "to": "shop-api-db-access"} in g["edges"]


def test_suggest_links_is_idempotent(store):
    a = suggest_links(store, 0.2, log=quiet)
    b = suggest_links(store, 0.2, log=quiet)
    assert a == b


def test_lang_picks_default_instructions(cfg, monkeypatch):
    from hippocampus.config import Config
    from hippocampus.i18n import norm
    assert cfg.lang == "en" and cfg.instructions.startswith("Long-term memory")
    monkeypatch.setenv("HIPPOCAMPUS_LANG", "pt-BR")
    pt = Config.from_env()
    assert pt.lang == "pt" and pt.instructions.startswith("Memória de longo prazo")
    assert norm("klingon") == "en"
