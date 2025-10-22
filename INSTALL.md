# Installation Guide

## Quick Install (Global)

### Step 1: Install the package globally

```bash
# From the project directory
uv tool install .
```

This will:
- Install the package in an isolated environment
- Make `playwright-proxy-server` and `playwright-proxy-client` available globally
- Store the installation in `~/.local/bin` (or equivalent on your system)

### Step 2: Verify installation

```bash
# Check that commands are available
which playwright-proxy-server
which playwright-proxy-client

# Test the client help
playwright-proxy-client --help
```

### Step 3: Configure your MCP client

Add this to your MCP client config (e.g., `~/.config/claude/config.json` or similar):

```json
{
  "mcpServers": {
    "playwright-proxy": {
      "command": "playwright-proxy-client"
    }
  }
}
```

### Step 4: Start the server

In a separate terminal:
```bash
playwright-proxy-server
```

That's it! Your MCP client can now communicate with the proxy.

## Alternative: Development Install

If you're developing or testing:

```bash
# Install in editable mode (from project directory)
uv pip install -e ".[dev]"

# Run commands with uv run
uv run playwright-proxy-server

# Configure MCP client with full path
{
  "mcpServers": {
    "playwright-proxy": {
      "command": "uv",
      "args": ["run", "--directory", "/full/path/to/playwright-mcp-proxy", "playwright-proxy-client"]
    }
  }
}
```

## Updating

### If installed with `uv tool install`:

```bash
# Update to latest version
cd /path/to/playwright-mcp-proxy
git pull  # if using git
uv tool upgrade playwright-mcp-proxy
```

Or reinstall:
```bash
uv tool uninstall playwright-mcp-proxy
uv tool install .
```

## Troubleshooting

### Command not found after `uv tool install`

UV tool binaries are installed to:
- **Linux/macOS**: `~/.local/bin`
- **Windows**: `%USERPROFILE%\.local\bin`

Add this to your PATH if not already:

```bash
# Add to ~/.bashrc, ~/.zshrc, or equivalent
export PATH="$HOME/.local/bin:$PATH"
```

Then reload your shell:
```bash
source ~/.bashrc  # or ~/.zshrc
```

### Verify UV tool installation location

```bash
uv tool dir
```

### Check installed tools

```bash
uv tool list
```

Should show:
```
playwright-mcp-proxy v0.1.0
- playwright-proxy-server
- playwright-proxy-client
```

## Complete Example (Fresh Install)

```bash
# 1. Clone or navigate to the project
cd playwright-mcp-proxy

# 2. Install globally
uv tool install .

# 3. Verify
playwright-proxy-client --help

# 4. Start server (in one terminal)
playwright-proxy-server

# 5. Configure your MCP client with:
#    { "command": "playwright-proxy-client" }

# 6. Use from your MCP client
#    > create_new_session()
#    > browser_navigate(url="https://example.com")
```

## Uninstall

```bash
uv tool uninstall playwright-mcp-proxy
```
