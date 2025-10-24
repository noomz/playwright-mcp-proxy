# Phase 7: Restart Recovery - Design Document

## Overview

Enable sessions to survive server restarts by persisting browser state and rehydrating on startup.

## Goals

1. **Persist session state** - Save browser state to SQLite
2. **Detect orphaned sessions** - Find unclosed sessions on startup
3. **Rehydrate sessions** - Restore browser state automatically
4. **Graceful degradation** - Handle cases where rehydration fails
5. **User control** - Provide tools to resume or abandon sessions

## Session State to Persist

### Essential State (Must Have)
- **Current URL** - Page the browser is on
- **Cookies** - All cookies for the domain
- **Local Storage** - localStorage key-value pairs
- **Session Storage** - sessionStorage key-value pairs

### Optional State (Nice to Have)
- **Viewport size** - Window dimensions
- **User agent** - Browser user agent string
- **Geolocation** - If set
- **Timezone** - If overridden

### Cannot Persist (Limitations)
- **Pending network requests** - In-flight XHR/fetch
- **JavaScript execution state** - Running timers, promises
- **Open dialogs** - alert(), confirm(), prompt()
- **File upload state** - Selected files
- **WebSocket connections** - Active socket connections

## Database Schema Changes

### sessions table updates
```sql
ALTER TABLE sessions ADD COLUMN current_url TEXT;
ALTER TABLE sessions ADD COLUMN cookies TEXT;  -- JSON array
ALTER TABLE sessions ADD COLUMN local_storage TEXT;  -- JSON object
ALTER TABLE sessions ADD COLUMN session_storage TEXT;  -- JSON object
ALTER TABLE sessions ADD COLUMN viewport TEXT;  -- JSON object {width, height}
ALTER TABLE sessions ADD COLUMN last_snapshot_time TIMESTAMP;
```

### session_snapshots table (new)
```sql
CREATE TABLE session_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    current_url TEXT,
    cookies TEXT,  -- JSON array
    local_storage TEXT,  -- JSON object
    session_storage TEXT,  -- JSON object
    viewport TEXT,  -- JSON object
    snapshot_time TIMESTAMP NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
);

CREATE INDEX idx_session_snapshots_session ON session_snapshots(session_id);
CREATE INDEX idx_session_snapshots_time ON session_snapshots(snapshot_time DESC);
```

## Capture Strategy

### When to Capture State

**Option A: On Every Action (Eager)**
- Pros: Always up-to-date, no data loss
- Cons: Performance overhead, many DB writes

**Option B: Periodic Snapshots (Lazy)**
- Pros: Lower overhead, configurable interval
- Cons: May lose recent actions, eventual consistency

**Option C: Hybrid (Recommended)**
- Capture on: navigate, major state changes
- Skip on: snapshot, click, type (unless config says otherwise)
- Configurable: `capture_interval` setting (default: 30s)

### Implementation Approach (Hybrid)

```python
async def capture_session_state(session_id: str, force: bool = False):
    """
    Capture current session state.

    Args:
        session_id: Session to capture
        force: Force capture even if interval not elapsed
    """
    # Check if enough time has passed since last capture
    session = await database.get_session(session_id)
    if not force:
        if session.last_snapshot_time:
            elapsed = (datetime.now() - session.last_snapshot_time).total_seconds()
            if elapsed < settings.session_snapshot_interval:
                return  # Skip, too soon

    # Get state from Playwright
    state = await playwright_manager.get_session_state()

    # Save to database
    await database.save_session_state(session_id, state)
```

## Playwright State Extraction

### Using Playwright MCP Tools

We need to add custom calls to Playwright to get state:

```javascript
// Get cookies
await page.context().cookies()

// Get localStorage
await page.evaluate(() => JSON.stringify(localStorage))

// Get sessionStorage
await page.evaluate(() => JSON.stringify(sessionStorage))

// Get current URL
await page.url()

// Get viewport
await page.viewportSize()
```

**Problem:** Playwright MCP may not expose direct access to `page` object.

**Solution:**
1. Add custom state extraction via browser_evaluate
2. OR: Extend Playwright MCP with state export tools
3. OR: Use browser_snapshot + parsing (less reliable)

### Recommended Approach

Add state extraction endpoints to our HTTP server that call Playwright:

```python
@app.get("/sessions/{session_id}/state")
async def get_session_state(session_id: str):
    """Get current browser state for session."""
    # Use browser_evaluate to get state
    state = {
        "url": await eval_script("window.location.href"),
        "localStorage": await eval_script("JSON.stringify(localStorage)"),
        "sessionStorage": await eval_script("JSON.stringify(sessionStorage)"),
        "cookies": await get_cookies(),
    }
    return state
```

## Rehydration Strategy

### On Server Startup

```python
async def startup_rehydration():
    """Detect and optionally rehydrate orphaned sessions."""

    # 1. Find sessions in 'active' state
    active_sessions = await database.get_sessions_by_state("active")

    for session in active_sessions:
        # 2. Get last snapshot
        snapshot = await database.get_latest_session_snapshot(session.session_id)

        if not snapshot:
            # No snapshot, mark as closed
            await database.update_session_state(session.session_id, "closed")
            continue

        # 3. Check snapshot age
        age = (datetime.now() - snapshot.snapshot_time).total_seconds()
        if age > settings.max_session_age:  # e.g., 24 hours
            # Too old, mark as stale
            await database.update_session_state(session.session_id, "stale")
            continue

        # 4. Attempt rehydration
        if settings.auto_rehydrate:
            success = await rehydrate_session(session.session_id, snapshot)
            if success:
                logger.info(f"Rehydrated session {session.session_id}")
            else:
                await database.update_session_state(session.session_id, "failed")
        else:
            # Mark as recoverable (user can manually resume)
            await database.update_session_state(session.session_id, "recoverable")
```

### Rehydration Process

```python
async def rehydrate_session(session_id: str, snapshot: SessionSnapshot) -> bool:
    """
    Restore browser state from snapshot.

    Returns:
        True if successful, False otherwise
    """
    try:
        # 1. Navigate to last URL
        await playwright_manager.send_request(
            "tools/call",
            {"name": "browser_navigate", "arguments": {"url": snapshot.current_url}}
        )

        # 2. Restore cookies
        cookies = json.loads(snapshot.cookies)
        for cookie in cookies:
            # Use browser_evaluate to set cookies
            await set_cookie(cookie)

        # 3. Restore localStorage
        if snapshot.local_storage:
            storage = json.loads(snapshot.local_storage)
            for key, value in storage.items():
                await eval_script(f"localStorage.setItem('{key}', '{value}')")

        # 4. Restore sessionStorage
        if snapshot.session_storage:
            storage = json.loads(snapshot.session_storage)
            for key, value in storage.items():
                await eval_script(f"sessionStorage.setItem('{key}', '{value}')")

        # 5. Reload page to apply storage
        await eval_script("location.reload()")

        return True

    except Exception as e:
        logger.error(f"Failed to rehydrate session {session_id}: {e}")
        return False
```

## New Tools

### session_resume(session_id)

```python
Tool(
    name="session_resume",
    description="Resume a recoverable session from previous server run",
    inputSchema={
        "type": "object",
        "properties": {
            "session_id": {"type": "string", "description": "Session ID to resume"}
        },
        "required": ["session_id"]
    }
)
```

### list_sessions()

```python
Tool(
    name="list_sessions",
    description="List all sessions (active, recoverable, stale)",
    inputSchema={
        "type": "object",
        "properties": {
            "state": {"type": "string", "description": "Filter by state", "enum": ["active", "recoverable", "stale", "closed", "all"]}
        }
    }
)
```

## Configuration Settings

```python
class Settings(BaseSettings):
    # ... existing settings ...

    # Phase 7: Session Recovery
    session_snapshot_interval: int = Field(default=30, description="Seconds between session snapshots")
    max_session_age: int = Field(default=86400, description="Max age in seconds for recoverable sessions (default 24h)")
    auto_rehydrate: bool = Field(default=False, description="Automatically rehydrate sessions on startup")
    max_session_snapshots: int = Field(default=10, description="Keep last N snapshots per session")
```

## Edge Cases

### 1. Multiple Server Instances
**Problem:** Two servers trying to rehydrate same session
**Solution:** Use SQLite row locking or file-based lock

### 2. Playwright Subprocess Crash
**Problem:** State capture fails mid-session
**Solution:** Last good snapshot used for recovery

### 3. Session Conflict
**Problem:** User creates new session with same session_id
**Solution:** Reject if session_id exists in 'active' or 'recoverable' state

### 4. Corrupted State
**Problem:** Invalid JSON in cookies/storage
**Solution:** Try rehydration, fall back to marking as failed

### 5. URL Changed During Capture
**Problem:** Navigate happens while capturing state
**Solution:** Use transaction or accept eventual consistency

## Implementation Phases

### Phase 7.1: State Capture (v0.3.0)
- Database schema updates
- State extraction from Playwright
- Periodic snapshot saving
- Tests for state capture

### Phase 7.2: Startup Detection (v0.3.1)
- Detect orphaned sessions on startup
- Mark sessions as recoverable/stale
- Add list_sessions tool

### Phase 7.3: Rehydration (v0.3.2)
- Implement rehydration logic
- Add session_resume tool
- Handle rehydration failures gracefully

### Phase 7.4: Testing & Polish (v0.3.3)
- Integration tests
- Edge case handling
- Performance optimization
- Documentation

## Success Criteria

- [ ] Sessions survive server restart
- [ ] State (URL, cookies, storage) accurately restored
- [ ] User can list and resume recoverable sessions
- [ ] Graceful handling when rehydration fails
- [ ] Configurable auto-rehydration
- [ ] Performance impact < 5% on normal operations
- [ ] Comprehensive documentation of limitations

## Limitations to Document

1. **Not Real-Time** - Snapshots may be up to `snapshot_interval` seconds old
2. **No Active State** - Running timers, pending requests lost
3. **Storage Only** - Cannot restore JavaScript heap/closures
4. **Best Effort** - Some sites may break if storage alone is restored
5. **No Dialog State** - Open alerts/confirms lost
6. **Cookie Domain** - Cookies may have domain restrictions
