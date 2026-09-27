# Using Hippocampus from claude.ai (web, desktop and mobile)

Claude Code talks to Hippocampus with a bearer token in a header. claude.ai
**custom connectors** cannot send custom headers, so Hippocampus can also
accept a secret embedded in the URL.

1. Generate a secret that is different from your token:

   ```bash
   hippocampus token
   ```

2. Put it in the server's `.env` and restart:

   ```
   HIPPOCAMPUS_URL_SECRET=<secret>
   ```

3. In claude.ai, open **Settings → Connectors → Add custom connector** and use:

   ```
   https://memory.example.com/mcp/<secret>
   ```

The same memory tools then become available in claude.ai chats, including on
your phone, and they read and write the same memories Claude Code uses.

> The URL now works as a password. Don't paste it in shared chats or
> screenshots. If it leaks, change `HIPPOCAMPUS_URL_SECRET` and update the
> connector.

The automatic recall hook exists only in Claude Code. In claude.ai, Claude
calls `search_memory` when the server's instructions tell it to. You can
customise those instructions with `HIPPOCAMPUS_INSTRUCTIONS_FILE`.
