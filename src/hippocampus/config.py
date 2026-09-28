"""Server configuration, read once from environment variables.

Everything that used to be hard-coded for a single machine (paths, domain,
owner name, token) lives here, so a fresh install only needs a `.env`.
"""
import os
from dataclasses import dataclass, field
from pathlib import Path

from .i18n import norm, text

# One folder per user for everything: the server's data and token, and the
# Claude Code client's config and hooks. A fixed place (not the current
# directory) is what lets the server start on its own at login.
HOME = Path.home() / ".hippocampus"
DEFAULT_TOKEN_FILE = HOME / "server-token"

DEFAULT_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


def _env(name, default=""):
    return os.environ.get("HIPPOCAMPUS_" + name, default).strip()


def _list(value):
    return [x.strip() for x in value.split(",") if x.strip()]


@dataclass
class Config:
    data_dir: Path
    memory_dir: Path
    db_path: Path
    web_dir: Path
    token: str
    token_file: Path
    model: str
    owner: str
    instructions: str
    lang: str
    host: str
    port: int
    allowed_hosts: list = field(default_factory=list)
    url_secret: str = ""
    pinned: str = ""

    @classmethod
    def from_env(cls):
        data = Path(_env("DATA_DIR", str(HOME / "data"))).expanduser()
        memory_dir = Path(_env("MEMORY_DIR", str(data / "memories"))).expanduser()
        token = _env("TOKEN")
        token_file = _env("TOKEN_FILE", str(DEFAULT_TOKEN_FILE))
        if not token and Path(token_file).exists():
            token = Path(token_file).read_text(encoding="utf-8").strip()

        port = int(_env("PORT", "8765"))
        hosts = _list(_env("ALLOWED_HOSTS"))
        public = _env("PUBLIC_URL").split("://")[-1].rstrip("/")
        if public:
            hosts += [public, public + ":443"]
        hosts += ["localhost:%d" % port, "127.0.0.1:%d" % port, "localhost", "127.0.0.1"]

        lang = norm(_env("LANG", "en"))
        owner = _env("OWNER", "the user")
        instructions = _env("INSTRUCTIONS")
        instructions_file = _env("INSTRUCTIONS_FILE")
        if not instructions and instructions_file and Path(instructions_file).exists():
            instructions = Path(instructions_file).read_text(encoding="utf-8").strip()
        if not instructions:
            instructions = text(lang, "instructions", owner=owner)

        return cls(
            data_dir=data,
            memory_dir=memory_dir,
            db_path=Path(_env("DB_PATH", str(data / "hippocampus.db"))).expanduser(),
            web_dir=Path(__file__).parent / "web",
            token=token,
            token_file=Path(token_file).expanduser(),
            model=_env("MODEL", DEFAULT_MODEL),
            owner=owner,
            instructions=instructions,
            lang=lang,
            host=_env("HOST", "127.0.0.1"),
            port=port,
            allowed_hosts=list(dict.fromkeys(hosts)),
            url_secret=_env("URL_SECRET"),
            pinned=_env("PINNED"),
        )
