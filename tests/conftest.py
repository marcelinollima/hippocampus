import hashlib
import re
import shutil
from pathlib import Path

import numpy as np
import pytest

from hippocampus.config import Config
from hippocampus.store import Store

EXAMPLES = Path(__file__).resolve().parent.parent / "examples" / "memories"
DIM = 256


def fake_embed(texts):
    """Deterministic bag-of-words vectors: no model download in tests or CI."""
    out = np.zeros((len(texts), DIM), dtype="float32")
    for i, t in enumerate(texts):
        for w in re.findall(r"\w{3,}", t.lower()):
            out[i, int(hashlib.md5(w.encode()).hexdigest(), 16) % DIM] += 1.0
    return out / (np.linalg.norm(out, axis=1, keepdims=True) + 1e-9)


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    for k in ("DATA_DIR", "MEMORY_DIR", "DB_PATH", "TOKEN", "PINNED", "URL_SECRET"):
        monkeypatch.delenv("HIPPOCAMPUS_" + k, raising=False)
    monkeypatch.setenv("HIPPOCAMPUS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("HIPPOCAMPUS_TOKEN", "test-token")
    monkeypatch.setenv("HIPPOCAMPUS_PINNED", "systems-map")
    monkeypatch.setenv("HIPPOCAMPUS_URL_SECRET", "s3cret")
    shutil.copytree(EXAMPLES, tmp_path / "memories")
    return Config.from_env()


@pytest.fixture
def store(cfg):
    s = Store(cfg, embedder=fake_embed)
    s.sync(log=lambda *_: None)
    return s
