"""
Chrome comparison tests: claude-in-chrome path vs proxy/direct paths.

Loads pre-recorded measurements from tests/chrome_measurements.json and generates
a formatted chrome-path performance report. Tests skip gracefully if the JSON
fixture has not been created yet.

Requirements:
    - tests/chrome_measurements.json must exist (created via Task 2: record chrome measurements)

Run:
    uv run pytest tests/test_chrome_comparison.py -v -s -m chrome_comparison

Produces a performance report showing chrome path metrics (navigate latency,
read_page payload/token estimates) across 3 scenarios.
"""

import json
import pathlib
from dataclasses import dataclass, field

import pytest

from tests.test_comparison import Measurement, ScenarioMetrics, _estimate_tokens, _format_table

# ---------------------------------------------------------------------------
# Path to pre-recorded chrome measurements fixture
# ---------------------------------------------------------------------------

CHROME_MEASUREMENTS_PATH = pathlib.Path(__file__).parent / "chrome_measurements.json"

# ---------------------------------------------------------------------------
# JSON fixture loader
# ---------------------------------------------------------------------------

# Expected JSON schema:
# {
#   "generated_at": "<ISO datetime string>",
#   "scenarios": [
#     {
#       "name": "<scenario name>",
#       "measurements": [
#         {
#           "label": "<operation label>",
#           "path": "chrome",
#           "elapsed_ms": <float>,
#           "payload_bytes": <int>,
#           "estimated_tokens": <int>
#         },
#         ...
#       ],
#       "notes": ["<optional note>", ...]  // optional
#     },
#     ...
#   ]
# }


def _load_chrome_measurements() -> list[ScenarioMetrics]:
    """Read chrome_measurements.json and return list of ScenarioMetrics.

    Validates required keys and converts raw dicts into typed dataclass instances.
    Raises ValueError if required fields are missing.
    """
    raw = json.loads(CHROME_MEASUREMENTS_PATH.read_text(encoding="utf-8"))

    if "scenarios" not in raw:
        raise ValueError("chrome_measurements.json missing top-level 'scenarios' key")

    scenarios: list[ScenarioMetrics] = []
    for i, scenario_dict in enumerate(raw["scenarios"]):
        if "name" not in scenario_dict:
            raise ValueError(f"Scenario at index {i} missing required key 'name'")
        if "measurements" not in scenario_dict:
            raise ValueError(
                f"Scenario '{scenario_dict.get('name', i)}' missing required key 'measurements'"
            )

        measurements: list[Measurement] = []
        for j, m_dict in enumerate(scenario_dict["measurements"]):
            for required_key in ("label", "path", "elapsed_ms"):
                if required_key not in m_dict:
                    raise ValueError(
                        f"Measurement {j} in scenario '{scenario_dict['name']}' "
                        f"missing required key '{required_key}'"
                    )
            measurements.append(
                Measurement(
                    label=m_dict["label"],
                    path=m_dict["path"],
                    elapsed_ms=float(m_dict["elapsed_ms"]),
                    payload_bytes=int(m_dict.get("payload_bytes", 0)),
                    estimated_tokens=int(m_dict.get("estimated_tokens", 0)),
                )
            )

        scenarios.append(
            ScenarioMetrics(
                name=scenario_dict["name"],
                measurements=measurements,
                notes=list(scenario_dict.get("notes", [])),
            )
        )

    return scenarios


# ---------------------------------------------------------------------------
# Session-scoped autouse fixture — summary banner
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True, scope="session")
def print_chrome_report():
    """Print a summary banner after all chrome_comparison tests complete."""
    yield

    if not CHROME_MEASUREMENTS_PATH.exists():
        return

    try:
        scenarios = _load_chrome_measurements()
    except Exception:
        return

    total_measurements = sum(len(s.measurements) for s in scenarios)
    scenario_names = [s.name for s in scenarios]

    print("\n")
    print("=" * 80)
    print("  CHROME PATH COMPARISON RESULTS")
    print("=" * 80)
    print(f"  Scenarios recorded: {len(scenarios)}")
    print(f"  Total measurements: {total_measurements}")
    print()
    for i, name in enumerate(scenario_names, 1):
        print(f"  {i}. {name}")
    print()

    for scenario in scenarios:
        print(f"{'─' * 80}")
        print(f"  {scenario.name}")
        print(f"{'─' * 80}")

        headers = ["Operation", "Path", "Latency (ms)", "Payload (bytes)", "Est. Tokens"]
        rows = []
        for m in scenario.measurements:
            rows.append([
                m.label,
                m.path,
                f"{m.elapsed_ms:.0f}",
                f"{m.payload_bytes:,}" if m.payload_bytes else "-",
                f"{m.estimated_tokens:,}" if m.estimated_tokens else "-",
            ])
        print(_format_table(headers, rows, col_align=["<", "<", ">", ">", ">"]))

        if scenario.notes:
            print()
            for note in scenario.notes:
                print(f"  >> {note}")
        print()

    print("=" * 80)
    print()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.chrome_comparison
def test_chrome_measurements_valid():
    """Validate chrome_measurements.json schema and content.

    Asserts:
      - At least 1 scenario exists
      - Each scenario has at least 1 measurement
      - All measurements have path == "chrome"
    """
    if not CHROME_MEASUREMENTS_PATH.exists():
        pytest.skip("chrome_measurements.json not found")

    scenarios = _load_chrome_measurements()

    assert len(scenarios) >= 1, "Expected at least 1 scenario in chrome_measurements.json"

    for scenario in scenarios:
        assert len(scenario.measurements) >= 1, (
            f"Scenario '{scenario.name}' has no measurements"
        )
        for m in scenario.measurements:
            assert m.path == "chrome", (
                f"Measurement '{m.label}' in scenario '{scenario.name}' "
                f"has path='{m.path}', expected 'chrome'"
            )


@pytest.mark.chrome_comparison
def test_chrome_comparison_report():
    """Load chrome measurements and print a formatted chrome-path performance table.

    Demonstrates chrome path metrics: navigate latency, read_page payload/token estimates.
    Chrome operates on an existing warm Chrome instance vs Playwright's cold headless start.
    """
    if not CHROME_MEASUREMENTS_PATH.exists():
        pytest.skip("chrome_measurements.json not found")

    scenarios = _load_chrome_measurements()
    assert len(scenarios) >= 1

    print("\n")
    print("=" * 80)
    print("  CHROME PATH PERFORMANCE TABLE")
    print("  (claude-in-chrome: operates on existing Chrome instance, warm cache)")
    print("=" * 80)

    for scenario in scenarios:
        print(f"\n{'─' * 80}")
        print(f"  Scenario: {scenario.name}")
        print(f"{'─' * 80}")

        headers = ["Operation", "Path", "Latency (ms)", "Payload (bytes)", "Est. Tokens"]
        rows = []
        for m in scenario.measurements:
            rows.append([
                m.label,
                m.path,
                f"{m.elapsed_ms:.0f}",
                f"{m.payload_bytes:,}" if m.payload_bytes else "-",
                f"{m.estimated_tokens:,}" if m.estimated_tokens else "-",
            ])

        print(_format_table(headers, rows, col_align=["<", "<", ">", ">", ">"]))

        if scenario.notes:
            print()
            for note in scenario.notes:
                print(f"  >> {note}")

    print(f"\n{'=' * 80}")
    print("  NOTE: Chrome path uses warm browser cache; Playwright paths use cold headless start.")
    print("=" * 80)
    print()
