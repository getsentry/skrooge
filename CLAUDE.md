# CLAUDE.md

## Project Overview

Skrooge is a CLI tool for estimating Kubernetes scaling costs on GCP. Given a deployment's replica count, CPU/memory changes, and instance type, it calculates how many additional GCP instances are needed and their cost across different pricing tiers.

**Repository**: `getsentry/skrooge`
**Language**: Python 3.8+
**License**: Apache 2.0

## Repository Structure

```
skrooge/
├── skrooge/                # Main package
│   ├── __main__.py         # Entry point for `python -m skrooge`
│   ├── cli.py              # Click CLI commands and options
│   ├── utils.py            # Core calculation logic (constrained resource, instance count, cost)
│   ├── render.py           # Output formatting (english, json)
│   ├── scraper.py          # GCP instance data scraper (generates instances.json)
│   └── instances.json      # Bundled GCP instance specs and regional pricing (~1MB)
├── tests/
│   ├── test_skrooge.py     # CLI integration tests (Click CliRunner)
│   └── test_utils.py       # Unit tests for calculation functions
├── scripts/
│   └── bump-version.sh     # Version bumping script
├── .github/workflows/      # CI/CD (test, publish, release, changelog)
├── pyproject.toml           # Project metadata, dependencies, tool config
├── .pre-commit-config.yaml  # Pre-commit hooks (ruff, whitespace, yaml)
└── .craft.yml               # Sentry Craft release configuration
```

## Development Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -e '.[lint,scrape,test]'
```

Dependency groups defined in `pyproject.toml`:
- **Core**: `click`, `click-log`
- **`[lint]`**: `ruff`
- **`[test]`**: `pytest`, `pytest-cov`
- **`[scrape]`**: `pandas`, `requests`, `lxml`

## Common Commands

```bash
# Run tests
pytest

# Run tests with coverage (as CI does)
pytest --cov=./ --cov-report=xml

# Lint
ruff check .

# Format
ruff format .

# Update GCP instance data
python3 skrooge/scraper.py > skrooge/instances.json
```

## Architecture

The codebase follows a simple three-module pattern:

- **`cli.py`**: Defines the Click CLI group and `estimate` command. Loads `instances.json`, validates instance types with fuzzy matching (`difflib`), and orchestrates the calculation pipeline.
- **`utils.py`**: Pure calculation functions:
  - `determine_constrained_resource()` — determines if CPU or memory is the limiting factor
  - `determine_instance_count_required()` — calculates how many instances are needed
  - `calculate_cost()` — computes hourly/monthly/yearly costs
- **`render.py`**: Output dispatching for `english` (human-readable) and `json` formats.

Data flow: CLI parses args → loads instance data → calls utils for calculations → passes result dict to render.

## Testing

Tests use `pytest`. CLI tests use Click's `CliRunner` for integration testing.

- `tests/test_skrooge.py`: CLI integration tests (version flag, invalid input handling, negative value normalization, cost output verification)
- `tests/test_utils.py`: Unit tests for `determine_constrained_resource` and `determine_instance_count_required` with a c2-standard-30 fixture

Test data uses a hardcoded `c2_standard_30_instance_data` dict rather than loading from `instances.json`.

## CI/CD

GitHub Actions workflows target `main` branch:

- **`python-package.yml`**: Runs lint (`ruff check .`) and tests (`pytest --cov`) across Python 3.9–3.12 on every push/PR to main. Uploads coverage to Codecov.
- **`publish.yml`**: Triggered by pushes to `release/**` branches. Runs tests, then builds and uploads to PyPI via OIDC.
- **`release.yml`**: Manual workflow dispatch using Sentry's Craft for version bumping, changelog generation, and GitHub releases.
- **`changelog-preview.yml`**: Previews changelog entries on PRs.

## Code Conventions

- **Linting/Formatting**: Ruff (configured in `pyproject.toml`). `skrooge/scraper.py` is excluded from linting.
- **Style**: PEP 8, snake_case for all functions and variables.
- **CLI framework**: Click with `click_log` for verbosity control.
- **Error handling**: `click.BadParameter` for user-facing errors, with fuzzy match suggestions via `difflib.get_close_matches`.
- **Logging**: Python stdlib `logging` module, wired through `click_log`.
- **Imports**: Standard library first, third-party second, local (relative) imports third.
- **No type annotations**: The codebase does not use type hints consistently.
- **Units**: CPU in milli-cores, memory in MiB. Instance specs use cores and GiB.

## Key Data

`instances.json` structure:
```json
{
  "<family>": {
    "<instance-type>": {
      "regions": {
        "<region>": {
          "ondemand": <float>,
          "sud": <float>,
          "preemptible": <float>,
          "cud-1y": <float>,
          "cud-3y": <float>
        }
      },
      "specs": {
        "cores": <int>,
        "memory": <float>,
        "local_ssd": <int>,
        "gpu": <int>,
        ...
      }
    }
  }
}
```

18 instance families, 254 instance types, 47+ GCP regions, 5 cost classes.

## Pre-commit Hooks

Configured in `.pre-commit-config.yaml`:
- Trailing whitespace removal
- End-of-file newline
- YAML syntax check
- Large file prevention
- Ruff lint and format
