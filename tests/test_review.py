import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "clients" / "claude-code"))
import review  # noqa: E402

from hippocampus.store import RELATED_THRESHOLD  # noqa: E402

FIX = ("Finance decided: the dashboard and the monthly report credit the order to whoever "
       "closed it. Report mismatch per salesperson fixed.")


@pytest.fixture
def low_threshold(monkeypatch):
    # bag-of-words test vectors sit lower than the real model's
    monkeypatch.setattr("hippocampus.store.RELATED_THRESHOLD", 0.40)
    assert RELATED_THRESHOLD > 0.40


def test_review_candidates_bring_newer_evidence(store, low_threshold):
    store.save("finance-decision", "Finance decided the salesperson rule", FIX, project="shop-api")
    (item,) = store.review_candidates()
    assert item["name"] == "orders-report-mismatch" and item["since"] == "2026-03-12"
    assert "Finance must decide" in item["body"]
    assert [e["name"] for e in item["evidence"]] == ["finance-decision"]
    assert "whoever closed" in item["evidence"][0]["excerpt"]


def test_older_memories_are_not_evidence(store, low_threshold, cfg):
    store.save("finance-decision", "Finance decided the salesperson rule", FIX, project="shop-api")
    c = store.connect()
    c.execute("UPDATE memories SET modified='2026-01-01T00:00:00Z' WHERE name='finance-decision'")
    c.commit()
    c.close()
    assert store.review_candidates()[0]["evidence"] == []


def test_long_body_keeps_start_and_end(store):
    body = "START " + "x" * 9000 + " NEWEST-NOTE"
    store.save("big-todo", "d", body, project="infra", status="pending")
    item = next(i for i in store.review_candidates() if i["name"] == "big-todo")
    assert item["body"].startswith("START") and item["body"].endswith("NEWEST-NOTE")
    assert len(item["body"]) < 6100


def test_review_endpoint_requires_token(store):
    from starlette.testclient import TestClient

    from hippocampus.server import create_app
    c = TestClient(create_app(store.cfg, store, warmup=False), base_url="http://localhost:8765")
    assert c.post("/api/review", json={}).status_code == 401
    r = c.post("/api/review", json={"project": "shop"},
               headers={"Authorization": "Bearer test-token"})
    assert [i["name"] for i in r.json()["items"]] == ["orders-report-mismatch"]


def fake_claude(answer):
    def run(cmd, **kw):
        assert "mcp__hippocampus__mark_memory" in cmd[cmd.index("--disallowedTools") + 1]
        assert kw["env"]["HIPPOCAMPUS_EXTRACTING"] == "1"
        return subprocess.CompletedProcess(cmd, 0, stdout="Here:\n" + json.dumps(answer))
    return run


ITEM = {"name": "a", "project": "p", "since": "2026-01-01", "last_note": "",
        "description": "d", "body": "b", "evidence": []}
CFG = {"server_name": "hippocampus", "owner": "me", "lang": "en"}


def test_judge_parses_answers_and_demands_a_quote(monkeypatch):
    monkeypatch.setattr(review.shutil, "which", lambda _: "claude")
    b = dict(ITEM, name="b")
    monkeypatch.setattr(review.subprocess, "run", fake_claude([
        {"name": "a", "verdict": "resolved", "reason": "done", "source": "self",
         "quote": "it is done"},
        {"name": "b", "verdict": "resolved", "reason": "seems done", "quote": ""}]))
    a_res, b_res = review.judge(CFG, [ITEM, b], "sonnet")
    assert a_res["verdict"] == "resolved" and a_res["apply"] is True
    assert b_res["verdict"] == "unsure" and b_res["apply"] is False  # no proof, no resolve


def test_judge_missing_answer_is_unsure(monkeypatch):
    monkeypatch.setattr(review.shutil, "which", lambda _: "claude")
    monkeypatch.setattr(review.subprocess, "run", fake_claude([]))
    assert review.judge(CFG, [ITEM], "sonnet")[0]["verdict"] == "unsure"


def test_apply_marks_only_approved(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(review._client, "post",
                        lambda cfg, route, payload, timeout: calls.append(payload) or {"ok": True})
    f = tmp_path / "r.json"
    f.write_text(json.dumps([
        {"name": "a", "verdict": "resolved", "reason": "done", "source": "self",
         "quote": "it is done", "apply": True},
        {"name": "b", "verdict": "resolved", "reason": "done", "quote": "q", "apply": False},
        {"name": "c", "verdict": "pending", "reason": "open", "quote": "", "apply": False}]))
    review.apply(CFG, f)
    assert [c["name"] for c in calls] == ["a"]
    assert calls[0]["status"] == "resolved" and "it is done" in calls[0]["note"]


def review_once(store, verdict="pending", quote=""):
    store.record_reviews([{"name": "orders-report-mismatch", "project": "shop-api",
                           "verdict": verdict, "reason": "r", "quote": quote}])
    # the example files are dated 2026-03; a review "now" is newer than all of
    # them, and anything saved later in the test is newer than the review
    c = store.connect()
    c.execute("UPDATE reviews SET reviewed_at='2026-06-01T00:00:00Z'")
    c.commit()
    c.close()


def test_changed_only_skips_what_did_not_move(store, low_threshold):
    assert len(store.review_candidates(changed_only=True)) == 1  # never reviewed
    review_once(store)
    assert store.review_candidates(changed_only=True) == []
    assert len(store.review_candidates()) == 1  # a full run still sees it


def test_newer_evidence_brings_it_back(store, low_threshold):
    review_once(store)
    store.save("finance-decision", "Finance decided the salesperson rule", FIX, project="shop-api")
    (item,) = store.review_candidates(changed_only=True)
    assert [e["name"] for e in item["evidence"]] == ["finance-decision"]


def test_editing_the_item_brings_it_back(store):
    review_once(store)
    store.mark("orders-report-mismatch", "pending", "Finance meeting moved.")
    assert len(store.review_candidates(changed_only=True)) == 1


def test_suggestion_shows_until_the_memory_changes(store):
    review_once(store, "resolved", "Finance chose who closed")
    (p,) = store.pending()
    assert p["suggest"]["quote"] == "Finance chose who closed"
    store.mark("orders-report-mismatch", "pending", "Not yet, finance reopened it.")
    assert store.pending()[0]["suggest"] is None


def test_auto_off_does_nothing(monkeypatch, capsys):
    monkeypatch.setenv("HIPPOCAMPUS_REVIEW", "off")
    monkeypatch.setenv("HIPPOCAMPUS_URL", "http://x")
    monkeypatch.setattr(sys, "argv", ["review.py", "--auto"])
    monkeypatch.setattr(review._client, "post", lambda *a: pytest.fail("must not call the server"))
    review.main()
    assert "off" in capsys.readouterr().out


def test_auto_apply_records_and_marks(monkeypatch, tmp_path):
    monkeypatch.setenv("HIPPOCAMPUS_REVIEW", "apply")
    monkeypatch.setenv("HIPPOCAMPUS_URL", "http://x")
    monkeypatch.setattr(review._client, "HOME", tmp_path)
    monkeypatch.setattr(sys, "argv", ["review.py", "--auto"])
    calls = []

    def post(cfg, route, payload, timeout):
        calls.append((route, payload))
        return {"items": [ITEM]} if route == "/api/review" else {"ok": True}
    monkeypatch.setattr(review._client, "post", post)
    monkeypatch.setattr(review, "judge", lambda cfg, batch, model: [dict(
        name="a", project="p", since="", description="", verdict="resolved", reason="done",
        source="self", quote="it is done", evidence=[], apply=True)])
    review.main()
    routes = [r for r, _ in calls]
    assert routes == ["/api/review", "/api/review/record", "/api/mark"]
    assert calls[0][1]["changed_only"] is True
