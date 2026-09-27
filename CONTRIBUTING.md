# Contributing

Thanks for helping! Issues and pull requests are welcome in **English or
Portuguese** (issues e PRs em português também são bem-vindos).

## Development setup

```bash
git clone https://github.com/marcelinollima/hippocampus && cd hippocampus
python -m venv .venv && . .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest                 # uses a fake embedder: no model download needed
ruff check .
```

To run against the real embedding model with the sample memories:

```bash
export HIPPOCAMPUS_TOKEN=dev HIPPOCAMPUS_DATA_DIR=./data
mkdir -p data && cp -r examples/memories data/
hippocampus serve      # http://127.0.0.1:8765, token "dev"
```

## Guidelines

- **Keep it small.** Hippocampus is meant to be read end to end in one sitting.
  A new dependency needs a strong reason.
- **Comments explain *why*.** Many lines exist because something broke in real
  use; say what broke. See [docs/design.md](docs/design.md) for the tone.
- **Hooks use the standard library only.** They run inside every Claude Code
  session, on any OS, and must fail silently.
- **Never commit real memories.** Tests and examples use fictional data only.
- Add or update a test for any behaviour change, and a line in `CHANGELOG.md`.

## Reporting bugs

Please include the version (`hippocampus --version`), how you run it (Docker,
systemd, local), and the relevant log lines (`docker compose logs hippocampus`,
`~/.hippocampus/*.log` on the client). **Redact hostnames and tokens.**
