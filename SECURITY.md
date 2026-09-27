# Security policy

## What is at stake

A memory server usually holds hostnames, database names, file paths, and
sometimes credentials, which is exactly what an attacker would want. Treat the
server and its token like the most sensitive system your memories describe.

## Deployment checklist

- [ ] `HIPPOCAMPUS_TOKEN` is long and random (`hippocampus token`) and is not reused anywhere.
- [ ] The app listens only on `127.0.0.1` (the default); a TLS proxy (Caddy) faces the internet.
- [ ] Port 8765 is closed in the firewall and cloud security list.
- [ ] `data/` is backed up and is **never** committed to git (it is in `.gitignore`).
- [ ] If you set `HIPPOCAMPUS_URL_SECRET`, you treat that URL as a password.
- [ ] `HIPPOCAMPUS_ALLOWED_HOSTS` / `HIPPOCAMPUS_PUBLIC_URL` list only your own domain.

## Prompt injection

Recalled memories are injected into Claude's context. Anyone who can write a
memory can therefore influence Claude. Hippocampus labels recalled text as
*notes, not instructions*, and the extraction prompt treats transcripts as
evidence only, but these are mitigations, not guarantees. Do not give write
access (the token) to people you would not let type into your Claude session.

## Reporting a vulnerability

Please **do not open a public issue**. Use GitHub's private
[security advisory](https://github.com/marcelinollima/hippocampus/security/advisories/new)
form. You will get an answer within 7 days.
