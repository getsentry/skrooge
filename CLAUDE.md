# CLAUDE.md

## Project Overview

Skrooge is a CLI tool for estimating Kubernetes scaling costs on GCP. Given a deployment's replica count, CPU/memory changes, and instance type, it calculates how many additional GCP instances are needed and their cost across different pricing tiers. `skrooge tui` does the same interactively, for several workloads at once.

**Repository**: `getsentry/skrooge`
**Language**: Python 3.11+
**License**: Apache 2.0

## Repository Structure

```
skrooge/
├── skrooge/                # Main package
│   ├── __main__.py         # Entry point for `python -m skrooge`
│   ├── cli.py              # Click CLI commands and options
│   ├── utils.py            # Core logic (instance lookup, constrained resource, instance count, cost)
│   ├── render.py           # Output formatting (english, json)
│   ├── tui.py              # Textual app for `skrooge tui` (live multi-workload estimates)
│   ├── scraper.py          # Generates, validates and diffs instances.json from the Cloud Billing Catalog API
│   ├── machine_types.py    # Hard-coded machine type specs the scraper uses
│   └── instances.json      # Bundled GCP instance specs and regional pricing (~1MB)
├── tests/
│   ├── test_skrooge.py     # CLI integration tests (Click CliRunner)
│   ├── test_tui.py         # TUI tests (Textual's run_test pilot) and workloads file handling
│   ├── test_utils.py       # Unit tests for calculation functions
│   ├── test_scraper.py     # Unit tests for SKU parsing, price mapping, validation and diffs
│   └── fixtures/           # Fixed data for tests: Cloud Billing Catalog API responses, and part of instances.json
├── scripts/
│   └── bump-version.sh     # Version bumping script (run by Craft; updates pyproject.toml and uv.lock)
├── .github/
│   ├── ISSUE_TEMPLATE/     # Issue form for missing instance types, linked from the unknown instance type error
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
- **Runtime**: `click`, `click-log`, `textual` (which brings `rich`)
- **`dev` group** (installed by default): `cogapp`, `pytest`, `pytest-cov`, `ruff`

The scraper only uses the standard library.

When changing dependencies, use `uv add`/`uv remove` (or edit `pyproject.toml` and run `uv lock`) and commit `uv.lock`; CI uses `uv sync --locked` and fails if the lockfile is stale.

## Common Commands

```bash
# Run tests
uv run pytest

# Run the TUI (loads and saves skrooge.json by default)
uv run skrooge tui

# Run tests with coverage (as CI does)
uv run pytest --cov --cov-report=xml

# Lint
uv run ruff check .

# Format
uv run ruff format .

# Regenerate the CLI help in README.md (CI pushes it to same-repo PR branches if you forget)
uv run cog -r README.md

# Build the sdist and wheel into dist/
uv build

# Update GCP instance data (needs an access token or a Cloud Billing API key)
GCP_BILLING_ACCESS_TOKEN="$(gcloud auth print-access-token)" uv run python -m skrooge.scraper scrape --output new.json
uv run python -m skrooge.scraper diff skrooge/instances.json new.json
```

## Architecture

The codebase follows a simple pattern of a calculation core with two front ends:

- **`cli.py`**: Defines the Click CLI group and the `estimate`, `regions` and `tui` commands (`tui` imports `tui.py` lazily so the others don't load Textual). `estimate` checks its flags (required, `--replicas` at least 1, or `--min-replicas` and `--max-replicas` instead for an autoscaling deployment, `--cpu` and `--mem` not both 0), then converts any `EstimateError` from the pipeline into `click.BadParameter`. `--region` takes its choices from `available_regions()` and uses `metavar="REGION"`, so `estimate --help` (and the README help generated from it) doesn't list every region and doesn't change when the price data does, and `RegionChoice`, whose error suggests similar regions instead of Click's list of every choice. `--packing-efficiency` sets the bin-packed estimate's packing efficiency for both resources, and `--cpu-packing-efficiency`/`--mem-packing-efficiency` override it for one. `regions` lists `available_regions()`, optionally filtered by instance type and cost class.
- **`utils.py`**: Shared constants (`COST_CLASSES`) and the calculation pipeline:
  - `load_instance_types()` (cached) / `available_regions()` — load `instances.json` and list the GCP regions it has pricing for, optionally only in one cost class or for one instance type
  - `find_instance_data()` — look up an instance type, raising `InstanceNotFoundError` with fuzzy-match suggestions (`difflib`)
  - `check_pricing()` — raises `PricingNotFoundError`, suggesting cost classes, similar regions, and the `regions` command for ones that have pricing. Not every instance type has every cost class in every region, so never index pricing without checking.
  - `determine_constrained_resource()` — determines if CPU or memory is the limiting factor
  - `determine_instance_count_required()` — calculates how many instances are needed
  - `calculate_cost()` — computes hourly/monthly/yearly costs for whole nodes
  - `resource_prices()` — the per-vCPU and per-GiB prices of an instance type, for bin-packed estimates. Uses `instances.json`'s top-level `resource_prices` when the scraper has recorded them, otherwise `derive_resource_prices()` solves for them with a least squares fit over the family's machine types. Shared-core types (`SHARED_CORE_INSTANCE_TYPES`) and GPU types (`machine_types.GPUS`) are never priced by resource (`priced_by_resource()`), and the prices must reproduce the machine type prices to within 1% (`adds_up()`), or there's no bin-packed estimate. Deriving also needs at least two memory-to-vCPU ratios in the family.
  - `calculate_resource_cost()` — the bin-packed cost by resource and in total, each resource divided by its packing efficiency (`{"cores": ..., "memory": ...}`, as everywhere it's passed around)
  - `calculate_estimate()` — runs the whole pipeline (rejecting shared-core instance types) and returns the result dict that `render` and the TUI consume, including `resource_costs` (None when the pricing can't be split). Every user-facing problem it finds is an `EstimateError`.
  - `calculate_autoscaling_estimate()` — runs `calculate_estimate()` at each replica count a `SCALING_PATTERNS` pattern reaches between min and max replicas (each pattern is `(share of the week, load)` levels, with load 0 at min and 1 at max, rounded up by `replicas_at()`), and returns the estimate at max replicas with `replicas`, `required_instance_count`, `costs` and `resource_costs` replaced by their weekly averages, plus an `autoscaling` key with the pattern and the estimates at min and max. Only the CLI uses it; the TUI doesn't support autoscaling.
- **`render.py`**: Output dispatching for `english` (human-readable) and `json` formats. `render_english()` hands estimates with an `autoscaling` key to `render_autoscaling_english()`.
- **`tui.py`**: `SkroogeApp`, a Textual app with an input form, an estimate panel (both cost models and every cost class for the selected workload, and `shape_costs()`, the other machine types in its family with as many vCPUs), a settings bar, and a workloads table with a net total, which `ctrl+y` copies with `markdown_table()`. `Workload` holds replicas and per-replica CPU and memory before and after the change (`replicas_before`, `cpu_after`, ...), keeping numeric fields as the text typed. `estimate_workload()` validates them and passes the total change to `calculate_estimate()` as one replica's. `Settings` holds the cluster-wide cost model (`whole-nodes` or `bin-packed`) and CPU and memory packing efficiencies, saved in the workloads file next to the workloads. In the TUI a negative change counts as a saving: with whole nodes, the sign of the constrained resource's change decides; bin-packed, each resource is signed by its own change (`signed_resource_costs()`). The CLI reports magnitudes only.

Data flow: CLI parses args → `calculate_estimate()` → result dict to render. The TUI recalculates every workload with `calculate_estimate()` on each input change.

Textual's `Input.Changed`, `Select.Changed`, and `DataTable.RowHighlighted` messages can arrive after the form or table has moved on (filling in the form posts them too). TUI handlers therefore read the widget's current value or cursor rather than the message's, which makes stale messages no-ops.

## Testing

Tests use `pytest`, configured in the native `[tool.pytest]` table in `pyproject.toml` with `strict = true` and `filterwarnings = ["error"]`, so any warning (including deprecations from Click) fails the suite. CLI tests use Click's `CliRunner` for integration testing; don't use `runner.isolated_filesystem()`, which is deprecated in Click 8.5.

- `tests/test_skrooge.py`: CLI integration tests (version flag, invalid input handling, negative value normalization, cost output verification, verbosity logging, autoscaling options, `regions` filters). Tests that check prices or which regions and cost classes exist use the `instance_data` fixture's fixed data, not the bundled `instances.json`, so the automated price updates don't break them. The fixture patches `load_instance_types` in each module that imports it.
- `tests/test_utils.py`: Unit tests for `determine_constrained_resource` and `determine_instance_count_required` with a c2-standard-30 fixture, plus instance lookup, resource prices, `calculate_estimate` and `calculate_autoscaling_estimate`
- `tests/test_tui.py`: Drives `SkroogeApp` headlessly with `App.run_test()`, in both cost models. Async tests are wrapped by the `app_test` decorator, which runs them with `asyncio.run`, so no pytest-asyncio is needed.
- `tests/test_scraper.py`: Unit tests for the scraper against `tests/fixtures/billing_catalog_skus.json`, with no network access

The constrained-resource and instance-count unit tests use a hardcoded `c2_standard_30_instance_data` dict rather than loading from `instances.json`. The other utils tests and the TUI tests use `tests/fixtures/instances.json`, a fixed copy of part of `instances.json` (us-central1 only); add any machine types a new test needs to it rather than reading the bundled data. The scraper fixture is in the Cloud Billing Catalog API's response shape, but its prices are synthetic; never put real or made-up prices in `instances.json` by hand.

## CI/CD

GitHub Actions workflows target `main` branch:

- **`python-package.yml`**: On every push/PR to main, runs these jobs: `lint` (`ruff check` and `ruff format --check`), `readme` (runs `cog -r README.md` on the PR's head commit, and fails if the help changed, so a stale commit can't be merged), `readme-push` (on same-repo PRs, except Dependabot's, which get no secrets, commits the README that `readme` regenerated and pushes it to the PR branch with the Sentry release bot's token; it's a separate job that never runs the PR's code, so that code can't steal the token), `test` (`pytest --cov` across Python 3.11–3.15, uploading coverage to Codecov), and `package` (`uv build`, then runs the CLI from the built wheel).
- **`publish.yml`**: Triggered by pushes to `release/**` branches. Runs tests, then builds with `uv build` and uploads `dist/*` as a workflow artifact named after the commit SHA, which Craft publishes to PyPI.
- **`release.yml`**: Manual workflow dispatch using Sentry's Craft for version bumping (via `scripts/bump-version.sh`, which needs uv), changelog generation, and GitHub releases.
- **`changelog-preview.yml`**: Previews changelog entries on PRs.
- **`update-instances.yml`**: Daily (and manual) run of the scraper, authenticated with workload identity federation when the `GCP_WORKLOAD_IDENTITY_PROVIDER` and `GCP_SERVICE_ACCOUNT` variables are set, otherwise the `GCP_BILLING_API_KEY` secret. It validates the output, runs the tests against it, and if `instances.json` changed, force-pushes a single commit on top of `main` to `automation/update-instances` and opens or updates one PR with the diff report as its description. It uses the Sentry release bot GitHub App's token, because PRs opened with `GITHUB_TOKEN` don't trigger CI. It never pushes to `main`.

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
- **README help**: The `--help` output in `README.md` is generated by [cog](https://cog.readthedocs.io/) from the `[[[cog ... ]]]` blocks; don't edit it by hand. Run `uv run cog -r README.md` after changing any command, option or help text.
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

20 instance families, 317 instance types and 5 cost classes. Specs for `c4d`, `n4d` and `n4a` come from `gcloud compute machine-types list`, so they only have `cores`, `memory` and `cpu`. m2 is priced as M1 plus GCP's on-demand "Memory Optimized Upgrade Premium" SKUs, added to every m2 cost class. Regions and cost classes come from the Cloud Billing Catalog API, so not every machine type has every cost class in every region. There's no SKU for sustained use discounts, so `sud` is the on-demand price with the family's multiplier from `SUD_MULTIPLIERS` in `scraper.py` applied to vCPUs and memory (not GPUs).

`resource_prices` holds the hourly price of one vCPU (`cores`) and one GiB (`memory`) for each family priced from GCP's per-vCPU and per-GiB SKUs (every family but `f1` and `g1`). A machine type's price is `cores * cores price + memory * memory price`, except for the GPU families `a2` and `g2`, whose machine prices also include their GPUs, and the shared-core `e2-micro`, `e2-small` and `e2-medium`, which are billed for 0.25, 0.5 and 1 vCPU. Code that walks the top-level keys as instance families must skip `resource_prices`.

## Pre-commit Hooks

Configured in `.pre-commit-config.yaml`:
- Trailing whitespace removal
- End-of-file newline
- YAML and TOML syntax checks
- Large file prevention
- Ruff lint and format
