# Quick Start Guide

## 5-Minute Setup

### 1. Install Globally (One Command)

```bash
uv tool install .
```

✓ Commands now available: `playwright-proxy-server` and `playwright-proxy-client`

### 2. Start the Server

Open a terminal and run:

```bash
playwright-proxy-server
```

You should see:
```
INFO:     Starting Playwright MCP Proxy server...
INFO:     Database initialized at ./proxy.db
INFO:     Playwright subprocess started with PID 12345
INFO:     Application startup complete.
INFO:     Uvicorn running on http://localhost:34501
```

Keep this terminal running.

### 3. Configure Your MCP Client

#### Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS):

```json
{
  "mcpServers": {
    "playwright-proxy": {
      "command": "playwright-proxy-client"
    }
  }
}
```

#### VS Code with Copilot Chat

Edit `.vscode/settings.json` or user settings:

```json
{
  "chat.mcp.servers": {
    "playwright-proxy": {
      "command": "playwright-proxy-client"
    }
  }
}
```

#### Generic MCP Client

Add to your MCP configuration file:

```json
{
  "mcpServers": {
    "playwright-proxy": {
      "command": "playwright-proxy-client"
    }
  }
}
```

### 4. Test It

In your MCP client, try:

```
> create_new_session()
Created session: abc-123-def-456

> browser_navigate(url="https://example.com")
✓ Request completed successfully
Ref ID: xyz-789
Page snapshot available. Use get_content('xyz-789')

> get_content(ref_id="xyz-789", search_for="Example Domain")
- heading "Example Domain"
```

## What Just Happened?

1. **Server** started on port 34501, spawned Playwright MCP subprocess
2. **MCP Client** connected via stdio, communicates with server over HTTP
3. **Session created** with unique UUID
4. **Request proxied** to Playwright, response saved to SQLite
5. **Content retrieved** from database with filtering

## Configuration (Optional)

Create `.env` in your working directory:

```bash
# Server
PLAYWRIGHT_PROXY_SERVER_PORT=34501

# Browser
PLAYWRIGHT_PROXY_PLAYWRIGHT_BROWSER=chrome
PLAYWRIGHT_PROXY_PLAYWRIGHT_HEADLESS=false

# Database
PLAYWRIGHT_PROXY_DATABASE_PATH=./proxy.db
```

## Architecture

```
Your MCP Client
      ↓ stdio
playwright-proxy-client (Python MCP server)
      ↓ HTTP (localhost:34501)
playwright-proxy-server (FastAPI)
      ↓ stdio
Playwright MCP (@playwright/mcp)
      ↓
Browser (Chrome/Firefox/Webkit)
```

All requests/responses stored in SQLite at `./proxy.db`.

## Advanced Usage

### View Stored Data

```bash
sqlite3 proxy.db
```

```sql
SELECT * FROM sessions;
SELECT * FROM requests;
SELECT * FROM responses;
```

### Run Server with Custom Config

```bash
PLAYWRIGHT_PROXY_SERVER_PORT=8080 playwright-proxy-server
```

### Check Server Health

```bash
curl http://localhost:34501/health
```

### Manual Testing (Without MCP Client)

```bash
# Terminal 1: Start server
playwright-proxy-server

# Terminal 2: Run example script
python examples/test_server.py
```

## Troubleshooting

**Commands not found?**
```bash
# Check PATH includes ~/.local/bin
echo $PATH

# Add to ~/.bashrc or ~/.zshrc if missing
export PATH="$HOME/.local/bin:$PATH"
```

**Server won't start?**
```bash
# Check if port is in use
lsof -i :34501

# Or use a different port
PLAYWRIGHT_PROXY_SERVER_PORT=8080 playwright-proxy-server
```

**Playwright subprocess fails?**
```bash
# Install Playwright browsers
npx playwright install chromium

# Or install the full package
npm install -g @playwright/mcp@latest
```

## Next Steps

- Read [README.md](README.md) for full documentation
- Check [.current-work.md](.current-work.md) for design details
- See [CHANGELOG.md](CHANGELOG.md) for version history
- Run tests: `uv run pytest`

## Updating

```bash
cd /path/to/playwright-mcp-proxy
git pull  # if using git
uv tool upgrade playwright-mcp-proxy
```

## Uninstalling

```bash
uv tool uninstall playwright-mcp-proxy
```
