# Connecting AI Tools via MCP

The ready MCP server exposes four tools any MCP-compatible AI can call:

| Tool | What it does |
|------|-------------|
| `scan_repo` | Run a full readiness scan, returns Red/Yellow/Green results with evidence |
| `list_checkpoints` | List all checkpoint definitions for a repo |
| `explain_checkpoint` | Get full detail on a specific checkpoint (great after a failure) |
| `aggregate_baselines` | Cross-repo heatmap from multiple baseline files |

## Install

```bash
pip install "readiness-as-code[mcp]"
```

Or from source:
```bash
pip install -e ".[mcp]"
```

Verify the server binary is available:
```bash
ready-mcp --help
```

---

## Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS)
or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "ready": {
      "command": "ready-mcp"
    }
  }
}
```

Restart Claude Desktop. You'll see the readiness tools in the tool picker.

---

## Cursor

Create or edit `.cursor/mcp.json` in your project:

```json
{
  "mcpServers": {
    "ready": {
      "command": "ready-mcp"
    }
  }
}
```

Or set it globally at `~/.cursor/mcp.json` to have it available in all projects.

---

## VS Code (GitHub Copilot / Continue / other MCP extensions)

Add to your VS Code `settings.json`:

```json
{
  "mcp.servers": {
    "ready": {
      "command": "ready-mcp",
      "args": []
    }
  }
}
```

---

## Windsurf (Codeium)

Add to `~/.codeium/windsurf/mcp_config.json`:

```json
{
  "mcpServers": {
    "ready": {
      "command": "ready-mcp"
    }
  }
}
```

---

## Any MCP-compatible client (generic)

The server uses stdio transport (stdin/stdout), which is the standard MCP transport.
Any client that supports MCP can launch it as:

```
command: ready-mcp
transport: stdio
```

---

## Usage examples

Once connected, ask your AI:

```
Scan this repository for readiness issues.
```

```
What checkpoints are defined for this service?
```

```
I got a failure on sec-001 — explain what it checks and how to fix it.
```

```
Aggregate these baselines and tell me which gaps are systemic:
  services/auth/.readiness/review-baseline.json
  services/api/.readiness/review-baseline.json
  services/worker/.readiness/review-baseline.json
```

---

## Without MCP: AI skills (manual)

If your AI tool doesn't support MCP yet, use the prompt-based skills in `ai-skills/`:

- `ai-skills/scan.instructions.md` — Guide the AI through a manual scan
- `ai-skills/author-checkpoints.instructions.md` — Generate checkpoint definitions from guidelines

These work with any AI: paste the file contents as a system prompt or reference the file directly.
