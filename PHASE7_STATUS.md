# Phase 7: Restart Recovery - Status Report

## Overview
Enable sessions to survive server restarts by persisting and rehydrating browser state.

---

## ✅ Completed (v0.3.0-dev)

### 1. Design Document (PHASE7_DESIGN.md)
- [x] Comprehensive architecture design
- [x] State capture strategy defined (hybrid approach)
- [x] Rehydration process documented
- [x] Edge cases identified
- [x] Implementation plan (4 sub-phases)

### 2. Database Schema
- [x] Extended sessions table with recovery fields:
  - `current_url`, `cookies`, `local_storage`, `session_storage`
  - `viewport`, `last_snapshot_time`
- [x] Extended state enum:
  - New states: `recoverable`, `stale`, `failed`
  - Existing: `active`, `closed`, `error`
- [x] Created session_snapshots table:
  - Historical snapshots with timestamps
  - Indexed by session_id and time

### 3. Data Models
- [x] SessionSnapshot model created
- [x] Session model extended with recovery fields
- [x] All fields optional (backward compatible)

### 4. Configuration
- [x] session_snapshot_interval: 30s default
- [x] max_session_age: 24h default
- [x] auto_rehydrate: false (manual by default)
- [x] max_session_snapshots: 10 default

---

## 🚧 In Progress

### Phase 7.1: State Capture Infrastructure
- [x] Schema and models
- [ ] Database operations for snapshots
- [ ] State extraction from Playwright
- [ ] Periodic snapshot mechanism

---

## 📋 Remaining Work

### Phase 7.1 (Current) - State Capture
**Goal:** Capture and persist browser state periodically

Remaining tasks:
1. **Database Operations** (next)
   - [ ] `save_session_snapshot()` - Save new snapshot
   - [ ] `get_latest_session_snapshot()` - Get most recent
   - [ ] `get_session_snapshots()` - Get all for session
   - [ ] `cleanup_old_snapshots()` - Keep only last N
   - [ ] `update_session_state_fields()` - Update inline fields

2. **State Extraction**
   - [ ] Add Playwright state extraction helper
   - [ ] `get_current_url()` via browser_evaluate
   - [ ] `get_cookies()` via context API
   - [ ] `get_local_storage()` via browser_evaluate
   - [ ] `get_session_storage()` via browser_evaluate
   - [ ] `get_viewport()` via Playwright API

3. **Periodic Snapshots**
   - [ ] Background task for periodic snapshots
   - [ ] Snapshot on navigation events
   - [ ] Respect snapshot_interval setting
   - [ ] Handle snapshot failures gracefully

4. **Testing**
   - [ ] Test schema migrations
   - [ ] Test snapshot CRUD operations
   - [ ] Test state extraction accuracy
   - [ ] Test periodic snapshot mechanism

### Phase 7.2 - Startup Detection
**Goal:** Detect orphaned sessions and mark as recoverable

Tasks:
- [ ] Startup hook in lifespan
- [ ] Detect sessions in 'active' state
- [ ] Check snapshot age
- [ ] Mark as recoverable/stale/closed
- [ ] Add `list_sessions()` tool
- [ ] List sessions by state filter

### Phase 7.3 - Rehydration
**Goal:** Restore browser state from snapshots

Tasks:
- [ ] `rehydrate_session()` function
- [ ] Navigate to saved URL
- [ ] Restore cookies via Playwright
- [ ] Restore localStorage via evaluate
- [ ] Restore sessionStorage via evaluate
- [ ] Set viewport size
- [ ] Add `session_resume(session_id)` tool
- [ ] Handle rehydration failures
- [ ] Update session state after rehydration

### Phase 7.4 - Testing & Polish
**Goal:** Production-ready with full test coverage

Tasks:
- [ ] Integration tests for full flow
- [ ] Test crash/restart scenarios
- [ ] Test edge cases (stale, conflicts)
- [ ] Performance testing
- [ ] Add example scripts
- [ ] Update README
- [ ] Update CHANGELOG
- [ ] Document limitations

---

## 🎯 Success Criteria

Phase 7 will be complete when:
- [ ] Sessions survive server restart
- [ ] State (URL, cookies, storage) accurately restored
- [ ] Users can list and resume recoverable sessions
- [ ] Graceful handling of rehydration failures
- [ ] Configurable auto-rehydration
- [ ] Performance impact < 5%
- [ ] Comprehensive documentation

---

## 📊 Progress Estimate

**Overall Phase 7:** ~25% complete

- Phase 7.1 (State Capture): ~30% complete
- Phase 7.2 (Detection): 0% complete
- Phase 7.3 (Rehydration): 0% complete
- Phase 7.4 (Testing): 0% complete

**Next immediate steps:**
1. Test schema changes work (schema migration)
2. Implement database snapshot operations
3. Add Playwright state extraction
4. Implement periodic snapshot mechanism

---

## 🚨 Known Limitations (by design)

These are acceptable limitations documented in PHASE7_DESIGN.md:

1. **Not Real-Time** - Snapshots may be up to snapshot_interval old
2. **No Active State** - Running timers, pending requests lost
3. **Storage Only** - Cannot restore JavaScript heap/closures
4. **Best Effort** - Some sites may break if storage alone is restored
5. **No Dialog State** - Open alerts/confirms lost
6. **Cookie Domains** - Cookies may have domain restrictions

---

## 📝 Notes

- All schema changes are backward compatible
- Existing sessions unaffected
- No breaking changes to API
- Feature can be disabled (auto_rehydrate=false)
- Manual resume always available via session_resume tool

---

Last Updated: 2025-10-24
Version: 0.3.0-dev (Phase 7.1 in progress)
