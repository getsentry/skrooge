# CLAUDE.md

## Project Overview

Skrooge is a CLI tool for estimating Kubernetes scaling costs on GCP. Given a deployment's replica count, CPU/memory changes, and instance type, it calculates how many additional GCP instances are needed and their cost across different pricing tiers.

**Repository**: `getsentry/skrooge`
**Language**: Python 3.11+
**License**: Apache 2.0

## Repository Structure

```
skrooge/
├── skrooge/                # Main package
│   ├── __main__.py         # Entry point for `python -m skrooge`
│   ├── cli.py              # Click CLI commands and options
│   ├── utils.py            # Core calculation logic (constrained resource, instance count, cost)
│   ├── render.py           # Output formatting (english, json)
│   ├── scraper.py          # Generates, validates and diffs instances.json from the Cloud Billing Catalog API
│   ├── machine_types.py    # Hard-coded machine type specs the scraper uses
│   └── instances.json      # Bundled GCP instance specs and regional pricing (~1MB)
├── tests/
│   ├── test_skrooge.py     # CLI integration tests (Click CliRunner)
│   ├── test_utils.py       # Unit tests for calculation functions
│   ├── test_scraper.py     # Unit tests for SKU parsing, price mapping, validation and diffs
│   └── fixtures/           # Cloud Billing Catalog API responses (synthetic prices) for scraper tests
├── scripts/
│   └── bump-version.sh     # Version bumping script (run by Craft; updates pyproject.toml and uv.lock)
├── .github/
│   ├── workflows/          # CI/CD (test, publish, release, changelog, price updates)
│   └── dependabot.yml      # Monthly grouped updates for GitHub Actions and uv.lock
├── pyproject.toml           # Project metadata, dependencies, tool config
├── uv.lock                  # Locked dependency versions (commit changes to this)
├── .pre-commit-config.yaml  # Pre-commit hooks (ruff, whitespace, yaml, toml)
└── .craft.yml               # Sentry Craft release configuration
```

## Development Setup

The project is managed with [uv](https://docs.astral.sh/uv/) and built with the `uv_build` backend.

```bash
uv sync
```

This creates `.venv` with the package (editable) and the `dev` group. Dependencies defined in `pyproject.toml`:
- **Runtime**: `click`, `click-log`
- **`dev` group** (installed by default): `pytest`, `pytest-cov`, `ruff`

The scraper only uses the standard library.

When changing dependencies, use `uv add`/`uv remove` (or edit `pyproject.toml` and run `uv lock`) and commit `uv.lock`; CI uses `uv sync --locked` and fails if the lockfile is stale.

## Common Commands

```bash
# Run tests
uv run pytest

# Run tests with coverage (as CI does)
uv run pytest --cov --cov-report=xml

# Lint
uv run ruff check .

# Format
uv run ruff format .

# Build the sdist and wheel into dist/
uv build

# Update GCP instance data (needs a Cloud Billing API key)
GCP_BILLING_API_KEY=... uv run python -m skrooge.scraper scrape --output new.json
uv run python -m skrooge.scraper diff skrooge/instances.json new.json
```

## Architecture

The codebase follows a simple three-module pattern:

- **`cli.py`**: Defines the Click CLI group and `estimate` command. Loads `instances.json` (cached by `load_instance_types()`), derives the `--region` choices from it, validates the instance type (with fuzzy matching via `difflib`) and that the chosen region and cost class have pricing, and orchestrates the calculation pipeline. Not every instance type has every cost class in every region, so never index pricing without checking.
- **`utils.py`**: Pure calculation functions:
  - `determine_constrained_resource()` — determines if CPU or memory is the limiting factor
  - `determine_instance_count_required()` — calculates how many instances are needed
  - `calculate_cost()` — computes hourly/monthly/yearly costs
- **`render.py`**: Output dispatching for `english` (human-readable) and `json` formats.

Data flow: CLI parses args → loads instance data → calls utils for calculations → passes result dict to render.

## Testing

Tests use `pytest`, configured in the native `[tool.pytest]` table in `pyproject.toml` with `strict = true` and `filterwarnings = ["error"]`, so any warning (including deprecations from Click) fails the suite. CLI tests use Click's `CliRunner` for integration testing; don't use `runner.isolated_filesystem()`, which is deprecated in Click 8.5.

- `tests/test_skrooge.py`: CLI integration tests (version flag, invalid input handling, negative value normalization, cost output verification, verbosity logging)
- `tests/test_utils.py`: Unit tests for `determine_constrained_resource` and `determine_instance_count_required` with a c2-standard-30 fixture

- `tests/test_scraper.py`: Unit tests for the scraper against `tests/fixtures/billing_catalog_skus.json`, with no network access

Test data uses a hardcoded `c2_standard_30_instance_data` dict rather than loading from `instances.json`. The scraper fixture is in the Cloud Billing Catalog API's response shape, but its prices are synthetic; never put real or made-up prices in `instances.json` by hand.

## CI/CD

GitHub Actions workflows target `main` branch:

- **`python-package.yml`**: On every push/PR to main, runs three jobs: `lint` (`ruff check` and `ruff format --check`), `test` (`pytest --cov` across Python 3.11–3.15, uploading coverage to Codecov), and `package` (`uv build`, then runs the CLI from the built wheel).
- **`publish.yml`**: Triggered by pushes to `release/**` branches. Runs tests, then builds with `uv build` and uploads `dist/*` as a workflow artifact named after the commit SHA, which Craft publishes to PyPI.
- **`release.yml`**: Manual workflow dispatch using Sentry's Craft for version bumping (via `scripts/bump-version.sh`, which needs uv), changelog generation, and GitHub releases.
- **`changelog-preview.yml`**: Previews changelog entries on PRs.
- **`update-instances.yml`**: Daily (and manual) run of the scraper with the `GCP_BILLING_API_KEY` secret. It validates the output, runs the tests against it, and if `instances.json` changed, force-pushes a single commit on top of `main` to `automation/update-instances` and opens or updates one PR with the diff report as its description. It uses the Sentry release bot GitHub App's token, because PRs opened with `GITHUB_TOKEN` don't trigger CI. It never pushes to `main`.

The step-by-step release process (changelog, running the Release workflow with an explicit version, approving in getsentry/publish) is documented in the "Releasing" section of `README.md`. Craft doesn't edit `CHANGELOG.md` here (no changelog policy is configured), and `.craft.yml`'s `minVersion: 1.8.1` means the Release workflow needs an explicit version, not `auto` or a bump keyword.

## Code Conventions

- **Linting/Formatting**: Ruff (configured in `pyproject.toml`) with the default rules plus `B`, `C4`, `I`, and `UP`.
- **GitHub Actions**: Pin every action to a full commit SHA with a `# vX.Y.Z` comment; Dependabot keeps them current.
- **Style**: PEP 8, snake_case for all functions and variables.
- **CLI framework**: Click with `click_log` for verbosity control.
- **Error handling**: `click.BadParameter` for user-facing errors, with fuzzy match suggestions via `difflib.get_close_matches`.
- **Logging**: Each module uses `logger = logging.getLogger(__name__)`; never log on the root logger. `cli.py` attaches `click_log` to the `skrooge` package logger, so `--verbosity` covers every module.
- **Package data**: Read bundled files with `importlib.resources.files("skrooge")`, not paths relative to `__file__`.
- **Imports**: Standard library first, third-party second, local (relative) imports third (enforced by ruff's `I` rules).
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
  },
  "resource_prices": {
    "<family>": {
      "<region>": {
        "<cost class>": {"cores": <float>, "memory": <float>}
      }
    }
  }
}
```

17 instance families, 220 instance types and 5 cost classes. Regions and cost classes come from the Cloud Billing Catalog API, so not every machine type has every cost class in every region. There's no SKU for sustained use discounts, so `sud` is the on-demand price with the family's multiplier from `SUD_MULTIPLIERS` in `scraper.py` applied to vCPUs and memory (not GPUs).

`resource_prices` holds the hourly price of one vCPU (`cores`) and one GiB (`memory`) for each family priced from GCP's per-vCPU and per-GiB SKUs (every family but `f1` and `g1`). A machine type's price is `cores * cores price + memory * memory price`, except for the GPU families `a2` and `g2`, whose machine prices also include their GPUs, and the shared-core `e2-micro`, `e2-small` and `e2-medium`, which are billed for 0.25, 0.5 and 1 vCPU. Code that walks the top-level keys as instance families must skip `resource_prices`.

## Pre-commit Hooks

Configured in `.pre-commit-config.yaml`:
- Trailing whitespace removal
- End-of-file newline
- YAML and TOML syntax checks
- Large file prevention
- Ruff lint and format
