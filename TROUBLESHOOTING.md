# Troubleshooting Guide

## Common Issues and Solutions

### 1. "Separator is found, but chunk is longer than limit" Error

**Symptoms:**
```
Error: Separator is found, but chunk is longer than limit
HTTP error: Client error '400 Bad Request'
```

**Cause:**
This error occurred in versions prior to 0.2.1 when Playwright responses exceeded MCP protocol message size limits.

**Solution:**
1. Ensure you're running version 0.2.1 or later:
   ```bash
   cd /path/to/playwright-mcp-proxy
   git pull  # If using git
   uv sync   # Update dependencies
   ```

2. Restart the HTTP server:
   ```bash
   # Stop any running server processes
   pkill -f playwright-proxy-server

   # Start the new server
   uv run playwright-proxy-server
   ```

3. Restart your MCP client:
   - **If using Claude Desktop:** Restart the Claude Desktop application
   - **If using custom MCP client:** Restart your client process
   - **If using global installation:** Run the client again

4. Verify the fix:
   ```bash
   # Test that the server is running with the fix
   uv run python examples/test_bug_fix.py
   ```

### 2. HTTP 400 Bad Request

**Symptoms:**
```
HTTP error: Client error '400 Bad Request'
```

**Common Causes:**

#### A. Invalid Session ID
The session might have expired or doesn't exist.

**Solution:**
```python
# Always create a new session before making requests
response = await http_client.post("http://localhost:34501/sessions")
session_id = response.json()["session_id"]
```

#### B. Malformed Request
The request doesn't match the expected schema.

**Solution:**
Check that your request has the correct format:
```json
{
  "session_id": "valid-uuid-here",
  "tool": "browser_navigate",
  "params": {
    "url": "https://example.com"
  }
}
```

### 3. Server Not Responding

**Symptoms:**
```
Connection refused
Connection timeout
```

**Solution:**

1. Check if server is running:
   ```bash
   curl http://localhost:34501/health
   ```

2. If not running, start it:
   ```bash
   uv run playwright-proxy-server
   ```

3. Check server logs:
   ```bash
   # If running in background
   tail -f /tmp/playwright-proxy-server.log
   ```

4. Verify port 34501 is not in use by another process:
   ```bash
   lsof -i :34501
   ```

### 4. Playwright Subprocess Crashes

**Symptoms:**
```json
{"status": "degraded", "playwright_subprocess": "down"}
```

**Solution:**

1. Check server logs for subprocess errors:
   ```bash
   tail -50 /tmp/playwright-proxy-server.log
   ```

2. Ensure Playwright is installed:
   ```bash
   npx @playwright/mcp@latest --version
   ```

3. Restart the server (it will auto-restart the subprocess):
   ```bash
   pkill -f playwright-proxy-server
   uv run playwright-proxy-server
   ```

### 5. Large Error Messages

**Symptoms:**
Error messages are truncated with `... (truncated, XXX total chars)`

**Explanation:**
This is expected behavior in v0.2.1+ to prevent MCP protocol violations. Full error messages are still stored in the database.

**To view full errors:**
```python
# Query the database directly
import aiosqlite

async with aiosqlite.connect("proxy.db") as db:
    async with db.execute(
        "SELECT error_message FROM responses WHERE ref_id = ?",
        (ref_id,)
    ) as cursor:
        row = await cursor.fetchone()
        if row:
            print(row[0])  # Full error message
```

### 6. MCP Client Connection Issues

**Symptoms:**
- MCP client can't connect to server
- "Connection refused" errors
- Timeout errors

**Solution:**

1. Verify server configuration:
   ```bash
   # Check .env file
   cat .env

   # Should have:
   # PLAYWRIGHT_PROXY_SERVER_HOST=localhost
   # PLAYWRIGHT_PROXY_SERVER_PORT=34501
   ```

2. If using remote server, update host:
   ```bash
   # In .env
   PLAYWRIGHT_PROXY_SERVER_HOST=0.0.0.0  # Listen on all interfaces
   ```

3. Restart both server and client after configuration changes.

## Debugging Tips

### Enable Debug Logging

Set log level to DEBUG:
```bash
# In .env
PLAYWRIGHT_PROXY_LOG_LEVEL=DEBUG
```

Restart the server to see detailed logs.

### Check Database State

```bash
# Connect to SQLite database
sqlite3 proxy.db

# List all sessions
SELECT session_id, state, created_at FROM sessions;

# Check recent requests
SELECT ref_id, tool_name, timestamp FROM requests ORDER BY timestamp DESC LIMIT 10;

# Check for errors
SELECT ref_id, error_message FROM responses WHERE status = 'error' LIMIT 10;
```

### Test HTTP Server Directly

Use the example scripts to test without MCP overhead:
```bash
# Test basic functionality
uv run python examples/test_server.py

# Test diff functionality
uv run python examples/test_diff.py

# Test bug fix
uv run python examples/test_bug_fix.py
```

### Monitor Resource Usage

```bash
# Check server process
ps aux | grep playwright-proxy-server

# Monitor Playwright subprocess
ps aux | grep playwright

# Check port usage
lsof -i :34501
```

## Getting Help

If you're still experiencing issues:

1. Check the [CHANGELOG.md](CHANGELOG.md) for recent changes
2. Review [README.md](README.md) for configuration options
3. Run tests: `uv run pytest`
4. Create an issue with:
   - Version number (`grep version pyproject.toml`)
   - Full error message
   - Steps to reproduce
   - Server logs
   - OS and Python version

## Version-Specific Notes

### v0.2.1
- Fixed MCP message size limit errors
- Error messages now truncated to 500 chars in MCP responses
- Full errors still stored in database

### v0.2.0
- Added diff-based content retrieval
- Requires database migration (automatic on startup)

### v0.1.0
- Initial release
- Basic functionality
