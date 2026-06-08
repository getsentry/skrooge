# Skrooge Architecture Review

## Overview

Skrooge is a Python CLI tool for estimating the cost impact of scaling Kubernetes deployments on GCP. Built with Click, it loads pre-scraped pricing data from a static JSON file and performs straightforward arithmetic to produce cost estimates.

**Codebase size:** ~2,000 LOC across 4 modules (excluding the 1,745-line scraper)

```
skrooge/
├── cli.py          # 197 lines — Click commands, input validation, orchestration
├── utils.py        #  42 lines — Pure calculation functions
├── render.py       #  27 lines — Output formatting (english, json)
├── scraper.py      # 1745 lines — GCP pricing data scraper (run offline)
├── instances.json  # ~1.7MB — Pre-scraped instance specs + regional pricing
└── __main__.py     #  Entry point
```

**Data flow:**
```
CLI args → load instances.json → validate instance type → calculate resource
constraint → determine instance count → compute cost → render output
```

---

## Findings

### 1. Hardcoded Region List Is Duplicated and Will Drift

The list of 32 GCP regions is hardcoded in `cli.py:63-100` as a `click.Choice`. The scraper independently defines regions in `scraper.py:64-71`. These two lists must be kept in sync manually, and both are disconnected from the regions actually present in `instances.json`.

**Recommendation:** Derive the valid region list from `instances.json` at startup. Load the JSON first, extract all unique region keys, and pass that as the choice set. This eliminates the duplication and automatically picks up new regions when the data file is regenerated.

```python
# Load instance data once, then derive valid regions
regions = set()
for family in instance_types.values():
    for inst in family.values():
        regions.update(inst.get("regions", {}).keys())
```

---

### 2. No Input Validation in Business Logic Layer

`utils.py` performs no validation. If `cpu` or `mem` is `0`, `determine_constrained_resource` raises a `ZeroDivisionError`. If a region or cost class key is missing from the instance data, `calculate_cost` raises a raw `KeyError`. All error handling currently lives in `cli.py`, meaning these functions cannot be safely reused as a library.

**Recommendation:** Add guards at the boundary of `utils.py` functions. Raise `ValueError` with clear messages for invalid inputs (zero cpu/mem, missing region, missing cost class). This makes the functions defensively correct independent of caller context.

---

### 3. The Scraper Is 71% of the Codebase but Excluded from Quality Tooling

`scraper.py` is 1,745 lines — the majority of the code — yet it is explicitly excluded from ruff linting in `pyproject.toml`:

```toml
[tool.ruff]
exclude = ["skrooge/scraper.py"]
```

It also uses `print()` instead of `logging`, has no type hints, and contains large hardcoded dictionaries for every instance family.

**Recommendation:** Either bring the scraper under linting (even if incrementally, via per-file ignores for specific rules) or extract it into a separate tool/package with its own quality standards. The current approach silently accumulates technical debt in the largest file.

---

### 4. No Type Hints on Public API

None of the functions in `cli.py`, `utils.py`, or `render.py` have type annotations. The data flowing through the system is nested dicts with implicit schemas — there is no formal definition of what an "instance data" dict looks like.

**Recommendation:** Add type hints to all public functions, at minimum. Define a `TypedDict` (or dataclass) for the instance data structure, the cost result, and the render data payload. This serves as living documentation and enables static analysis.

```python
from typing import TypedDict

class InstanceSpecs(TypedDict):
    cores: int
    memory: float
    benchmark: int
    # ...

class CostResult(TypedDict):
    hourly: float
    monthly: int
    yearly: int
    class_: str
    region: str
```

---

### 5. Inconsistent Logging

Three different logging approaches are used across the codebase:

| Module | Approach |
|--------|----------|
| `cli.py` | `logger = logging.getLogger(__name__)` via click-log |
| `utils.py` | `logging.info()` (root logger) |
| `scraper.py` | `print()` |

`utils.py` logging goes to the root logger rather than a module-specific logger, which means it won't respect the verbosity option configured in `cli.py`.

**Recommendation:** Use `logging.getLogger(__name__)` consistently in every module. Replace `print()` in the scraper with proper logging as well.

---

### 6. `render()` Uses Sequential `if` Instead of `elif`

In `render.py:6-11`:

```python
def render(format, data):
    if format == "english":
        render_english(data)
    if format == "json":
        render_json(data)
```

Both conditions are evaluated independently. While this doesn't cause a bug today (the format values are mutually exclusive), it's a latent issue — adding a new format or using the function incorrectly won't produce an error.

**Recommendation:** Use `elif` / `else` with an explicit error for unknown formats:

```python
def render(format, data):
    if format == "english":
        render_english(data)
    elif format == "json":
        render_json(data)
    else:
        raise ValueError(f"Unknown format: {format}")
```

---

### 7. Instance Data Loaded on Every Invocation Without Caching

`cli.py:125-126` loads and parses the 1.7MB `instances.json` on every command invocation. For a CLI tool this is acceptable, but if skrooge is ever used as a library or in a loop, this becomes a bottleneck.

**Recommendation:** Use `functools.lru_cache` or load-once-at-module-level pattern to avoid repeated parsing. Low priority for CLI usage, but worth noting for library reuse.

---

### 8. Instance Family Parsing Is Fragile

`cli.py:119`:

```python
instance_family = instance.split("-")[0]
```

This assumes the instance name always follows the pattern `{family}-{type}-{size}`. If a user passes something like `custom-n2-standard-32` or a typo without a hyphen, the parsing silently produces wrong results.

**Recommendation:** Validate the parsed family against known families immediately after splitting, and provide a clear error if it doesn't match.

---

### 9. `--format` Help Text Is Wrong

`cli.py:108`:

```python
@click.option(
    "-f",
    "--format",
    help="The instance type this deployment is running on",  # Copy-paste error
```

The help text for `--format` says "The instance type this deployment is running on" — it was copied from the `--instance` option.

**Recommendation:** Fix the help text to describe the output format option.

---

### 10. Test Coverage Gaps

The test suite has 11 tests across 2 files, but:

- **No tests for `render.py`** — output formatting is untested
- **No tests for zero/missing inputs** — the `ZeroDivisionError` in `determine_constrained_resource` when cpu=0 or mem=0 is not covered
- **No tests for invalid region/cost-class combinations** at the `calculate_cost` level
- **Test data is hardcoded** in `test_utils.py` (~308 lines of fixture data) rather than using pytest fixtures or shared test data

**Recommendation:** Add tests for `render.py` (verify output strings contain expected values). Add edge-case tests for zero inputs and missing data keys. Extract test instance data into a `conftest.py` fixture for reuse.

---

### 11. No Multi-Cloud Support Path

The entire architecture is tightly coupled to GCP: instance naming conventions, pricing models (SUD, CUD), region names, and the scraper. There is no abstraction layer that would allow adding AWS or Azure support.

**Recommendation:** If multi-cloud is a future goal, introduce a provider abstraction early — a common interface for loading instance data and pricing regardless of cloud provider. If multi-cloud is explicitly not a goal, this is a non-issue.

---

## Summary

| # | Finding | Severity | Effort |
|---|---------|----------|--------|
| 1 | Duplicated region list | Medium | Low |
| 2 | No validation in utils.py | Medium | Low |
| 3 | Scraper excluded from linting | Medium | Medium |
| 4 | No type hints | Low | Medium |
| 5 | Inconsistent logging | Low | Low |
| 6 | `if` instead of `elif` in render | Low | Low |
| 7 | JSON loaded every invocation | Low | Low |
| 8 | Fragile instance family parsing | Low | Low |
| 9 | Wrong help text on `--format` | Low | Low |
| 10 | Test coverage gaps | Medium | Medium |
| 11 | No multi-cloud abstraction | Low | High |

The codebase is well-structured for its size and purpose. The separation between CLI, business logic, rendering, and data scraping is clean. The primary areas for improvement are defensive programming in `utils.py`, eliminating the duplicated region list, bringing the scraper under quality tooling, and expanding test coverage.
