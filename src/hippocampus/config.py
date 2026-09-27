"""Server configuration, read once from environment variables.

Everything that used to be hard-coded for a single machine (paths, domain,
owner name, token) lives here, so a fresh install only needs a `.env`.
"""
import os
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

DEFAULT_INSTRUCTIONS = """\
Long-term memory shared by every Claude session of {owner}: servers, databases,
projects, decisions and the recipes that are known to work.

READ: call search_memory before touching any server, database or system of
{owner}. The approved way of doing it is probably already written down here.

WRITE: new memories go through save_memory, NOT to local files, so they are
visible from every machine and every project. Set `project` to the project the
fact belongs to, `type` to one of project/reference/feedback/user, and link to
existing memories with [[other-memory-name]] in the body. Hand-written links
carry relationships that similarity search cannot infer.

VALIDITY: every memory has a status (active | pending | resolved | superseded).
When something a memory listed as pending gets done, call mark_memory with
status resolved and a short note; otherwise it keeps showing up as open. New
memories about unfinished work start as pending. For "what is still pending?",
use list_pending."""


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
    model: str
    owner: str
    instructions: str
    host: str
    port: int
    allowed_hosts: list = field(default_factory=list)
    url_secret: str = ""
    pinned: str = ""

    @classmethod
    def from_env(cls):
        data = Path(_env("DATA_DIR", str(Path.cwd() / "data"))).expanduser()
        memory_dir = Path(_env("MEMORY_DIR", str(data / "memories"))).expanduser()
        token = _env("TOKEN")
        token_file = _env("TOKEN_FILE")
        if not token and token_file and Path(token_file).exists():
            token = Path(token_file).read_text(encoding="utf-8").strip()

        port = int(_env("PORT", "8765"))
        hosts = _list(_env("ALLOWED_HOSTS"))
        public = _env("PUBLIC_URL").split("://")[-1].rstrip("/")
        if public:
            hosts += [public, public + ":443"]
        hosts += ["localhost:%d" % port, "127.0.0.1:%d" % port, "localhost", "127.0.0.1"]

        owner = _env("OWNER", "the user")
        instructions = _env("INSTRUCTIONS")
        instructions_file = _env("INSTRUCTIONS_FILE")
        if not instructions and instructions_file and Path(instructions_file).exists():
            instructions = Path(instructions_file).read_text(encoding="utf-8").strip()
        if not instructions:
            instructions = DEFAULT_INSTRUCTIONS.format(owner=owner)

        return cls(
            data_dir=data,
            memory_dir=memory_dir,
            db_path=Path(_env("DB_PATH", str(data / "hippocampus.db"))).expanduser(),
            web_dir=Path(__file__).parent / "web",
            token=token,
            model=_env("MODEL", DEFAULT_MODEL),
            owner=owner,
            instructions=instructions,
            host=_env("HOST", "127.0.0.1"),
            port=port,
            allowed_hosts=list(dict.fromkeys(hosts)),
            url_secret=_env("URL_SECRET"),
            pinned=_env("PINNED"),
        )
