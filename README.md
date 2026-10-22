# skrooge

[![PyPI](https://img.shields.io/pypi/v/skrooge.svg)](https://pypi.org/project/skrooge/)
[![Changelog](https://img.shields.io/github/v/release/getsentry/skrooge?include_prereleases&label=changelog)](https://github.com/getsentry/skrooge/releases)
[![Tests](https://github.com/getsentry/skrooge/actions/workflows/python-package.yml/badge.svg)](https://github.com/getsentry/skrooge/actions/workflows/python-package.yml)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](https://github.com/getsentry/skrooge/blob/main/LICENSE)

A quick and dirty kubernetes cost estimator

![OIG 0uCanRKKeLq7XwJysZQ3](https://github.com/getsentry/skrooge/assets/67560/8ba2d274-4281-43a0-ad75-f0838e29e5f4)
*Ebenezer scrooge standing at the helm of a ship, pencil sketch*


## Why

Scaling a Kubernetes deployment up or down changes how many nodes it needs, so it changes what you pay. Working that out by hand is grunt work every time: look up the node's machine type, figure out whether the change is CPU-bound or memory-bound, count the extra nodes, and price them. skrooge does that arithmetic for you using bundled GCP machine specs and regional pricing.

For example, doubling a deployment of 2 CPU / 3GiB pods from 16 to 32 replicas on `c2-standard-30` nodes (30 cores, 120GiB) adds 32 cores and 48GiB of memory. CPU runs out first, so it needs `ceil(32 / 30) = 2` more nodes:

    $ uvx skrooge estimate --replicas 16 --cpu 2000 --mem 3072 --instance c2-standard-30
    This workload is running on c2-standard-30 instances in us-central1 with 30 cores and 120GiB of memory.
    This workload will require 32.0 cores and 48.0 GiB of memory. This workload is cores-constrained.
    This workload will require 2 instances, costing $2.51/h (or $1829/m (or $21950/y)) at sud rates.

For a scale-down, pass the size of the reduction: the cost skrooge reports is what you'd save.

It's a quick estimate, not a bill. It assumes pods pack perfectly onto whole nodes, and it ignores the node capacity reserved for the system and DaemonSets, cluster autoscaler behaviour, and storage or network costs. Prices come from a snapshot in `skrooge/instances.json`, taken whenever that file was last regenerated.

## Installation

skrooge requires Python 3.11 or newer. The quickest way to use it is to run it with [`uvx`](https://docs.astral.sh/uv/guides/tools/), which fetches and runs the latest release without installing it:

    uvx skrooge --help

To install it as a standalone tool instead, use `uv`:

    uv tool install skrooge

Or with `pipx` or `pip`:

    pipx install skrooge
    pip install skrooge

## Usage

Estimate the cost of adding 5.81 cores and 9950MiB of memory to each of 1000 replicas running on `n2-highcpu-64` nodes:

    $ uvx skrooge estimate --replicas 1000 --cpu 5810 --mem 9950 --instance n2-highcpu-64
    This workload is running on n2-highcpu-64 instances in us-central1 with 64 cores and 64GiB of memory.
    This workload will require 5810.0 cores and 9716.796875 GiB of memory. This workload is memory-constrained.
    This workload will require 152 instances, costing $278.98/h (or $203658/m (or $2443898/y)) at sud rates.

Use `--region`, `--cost-class`, and `--format json` to change the region, pricing tier, and output format:

    uvx skrooge estimate --replicas 1000 --cpu 5810 --mem 9950 --instance n2-highcpu-64 --region europe-west1 --cost-class cud-1y --format json

If you installed skrooge, drop the `uvx` prefix and run `skrooge` directly (or `python -m skrooge`).

For help, run:

    uvx skrooge --help
    uvx skrooge estimate --help

## Development

This project uses [`uv`](https://docs.astral.sh/uv/) to manage its environment. To contribute, check out the code and install the dependencies:

    cd skrooge
    uv sync

To run the tests:

    uv run pytest

To lint and format:

    uv run ruff check .
    uv run ruff format .

To run the same checks automatically on each commit, install the [pre-commit](https://pre-commit.com/) hooks:

    uv tool install pre-commit
    pre-commit install

To update the instances.json file:

    uv run --group scrape python skrooge/scraper.py > skrooge/instances.json

## Releasing

Releases are made with Sentry's [Craft](https://github.com/getsentry/craft) and follow [Semantic Versioning](https://semver.org/). Anything that drops support for a Python version needs at least a minor version bump.

1. **Update the changelog.** Craft doesn't edit `CHANGELOG.md` for this project, so in a PR, rename the `## [Unreleased]` heading to `## [X.Y.Z] - YYYY-MM-DD`, add a new empty `## [Unreleased]` heading above it, and merge it to `main`. Make sure CI on `main` is green.
2. **Start the release.** In GitHub, go to **Actions → Release → Run workflow**, run it on `main`, and enter the new version, e.g. `1.1.0`. Enter an explicit version: `auto` and bump keywords like `minor` need a newer `minVersion` in `.craft.yml` than this project sets. Leave **force** empty unless you need to release despite an open issue labelled `release-blocker`.
3. **Craft prepares the release.** It creates a `release/X.Y.Z` branch from `main`, runs `scripts/bump-version.sh` (which uses `uv version` to update `pyproject.toml` and `uv.lock`), commits that as `release: X.Y.Z`, and opens a `publish: getsentry/skrooge@X.Y.Z` issue in [getsentry/publish](https://github.com/getsentry/publish).
4. **CI builds the package.** The push to `release/X.Y.Z` runs the [Publish Python Package](.github/workflows/publish.yml) workflow, which runs the tests and uploads the built sdist and wheel as an artifact for Craft. Wait for it to pass; the publish issue links to the check runs.
5. **Approve the release.** Add the `accepted` label to the publish issue. Craft then uploads the package to PyPI, tags the release and creates a GitHub release, and merges the release branch back into `main`. To call the release off before then, the person who started it can comment `#retract` on its own line in the publish issue.
6. **Check it.** Once PyPI has the new version, `uvx skrooge@X.Y.Z --version` should print it.
