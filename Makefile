.PHONY: install install-dev install-global uninstall reinstall \
       server client health \
       test test-unit test-integration lint fix \
       clean

# Setup
install:
	uv pip install -e .

install-dev:
	uv pip install -e ".[dev]"

install-global:
	uv tool install .

uninstall:
	uv tool uninstall playwright-mcp-proxy

reinstall:
	uv tool uninstall playwright-mcp-proxy || true
	uv cache clean --force playwright-mcp-proxy
	uv tool install .

# Run
server:
	uv run playwright-proxy-server

client:
	uv run playwright-proxy-client

health:
	playwright-proxy-ctl health

# Test
test:
	uv run pytest

test-unit:
	uv run pytest tests/test_database.py tests/test_diff.py tests/test_bugs.py tests/test_ctl.py -v

test-integration:
	uv run pytest tests/test_integration_live.py -v

lint:
	uv run ruff check .

fix:
	uv run ruff check --fix .

# Cleanup
clean:
	rm -f *.db*
	rm -rf __pycache__ .pytest_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
