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

Not every instance type has every cost class in every region. To list the regions with pricing for an instance type and cost class:

    uvx skrooge regions --instance n2-highcpu-64 --cost-class cud-1y

If you installed skrooge, drop the `uvx` prefix and run `skrooge` directly (or `python -m skrooge`).

### Command reference

The help for every command:

<!-- [[[cog
import cog
from click.testing import CliRunner
from skrooge.cli import cli

def show_help(*args):
    # Click wraps help at 78 columns in any terminal at least 80 columns wide
    result = CliRunner().invoke(cli, [*args, "--help"], prog_name="skrooge", terminal_width=78)
    assert result.exit_code == 0, result.output
    cog.out(f"```\n$ skrooge {' '.join([*args, '--help'])}\n{result.output}```\n")

show_help()
show_help("estimate")
show_help("regions")
]]] -->
```
$ skrooge --help
Usage: skrooge [OPTIONS] COMMAND [ARGS]...

  A quick and dirty kubernetes cost estimator

Options:
  --version  Show the version and exit.
  --help     Show this message and exit.

Commands:
  estimate  Quick estimate of the cost or savings a kubernetes scale...
  regions   List the regions skrooge has pricing for
```
```
$ skrooge estimate --help
Usage: skrooge estimate [OPTIONS]

  Quick estimate of the cost or savings a kubernetes scale update will incur

Options:
  -v, --verbosity LVL             Either CRITICAL, ERROR, WARNING, INFO or
                                  DEBUG
  -r, --replicas INTEGER RANGE    The number of replicas in the deployment
                                  [x>=1; required]
  -c, --cpu INTEGER               The amount of CPU change in milli-cores
                                  [required]
  -m, --mem INTEGER               The amount of memory change in MiB
                                  [required]
  -i, --instance TEXT             The instance type this deployment is running
                                  on  [required]
  --cost-class [sud|ondemand|preemptible|cud-1y|cud-3y]
                                  The type of cost to calculate. Default: sud
  --region REGION                 The region to use for cost calculation.
                                  Default: us-central1. List them with:
                                  skrooge regions
  -f, --format [english|json]     The output format. Default: english
  --help                          Show this message and exit.
```
```
$ skrooge regions --help
Usage: skrooge regions [OPTIONS]

  List the regions skrooge has pricing for

Options:
  -i, --instance TEXT             Only list regions with pricing for this
                                  instance type
  --cost-class [sud|ondemand|preemptible|cud-1y|cud-3y]
                                  Only list regions with pricing in this cost
                                  class
  --help                          Show this message and exit.
```
<!-- [[[end]]] -->

## Development

This project uses [`uv`](https://docs.astral.sh/uv/) to manage its environment. To contribute, check out the code and install the dependencies:

    cd skrooge
    uv sync

To run the tests:

    uv run pytest

To lint and format:

    uv run ruff check .
    uv run ruff format .

The CLI help in the [command reference](#command-reference) is generated with [cog](https://cog.readthedocs.io/). After changing a command or option, update it with:

    uv run cog -r README.md

If you forget, CI's `readme` check fails. On a pull request from a branch in this repository, CI also commits the regenerated help to the branch for you; on pull requests from forks, run cog yourself.

To run the same checks automatically on each commit, install the [pre-commit](https://pre-commit.com/) hooks:

    uv tool install pre-commit
    pre-commit install

### Updating prices

The [Update instance data](.github/workflows/update-instances.yml) workflow runs daily. It regenerates `skrooge/instances.json` from GCP's [Cloud Billing Catalog API](https://cloud.google.com/billing/docs/how-to/get-pricing-information-api) and, when anything changed, opens or updates a pull request from the `automation/update-instances` branch. The pull request description reports added and removed machine types, regions and cost classes, and flags prices that changed by more than 20%; review those before merging. Spot (`preemptible`) price changes are listed too, but not flagged, as Spot prices change often. It authenticates with [workload identity federation](https://github.com/google-github-actions/auth#preferred-direct-workload-identity-federation) when the `GCP_WORKLOAD_IDENTITY_PROVIDER` and `GCP_SERVICE_ACCOUNT` repository variables are set. The service account needs no roles, but its project needs the Cloud Billing API enabled. Otherwise it uses a `GCP_BILLING_API_KEY` repository secret holding an API key that's restricted to the Cloud Billing API.

To regenerate the data locally, with your `gcloud` login or an API key:

    GCP_BILLING_ACCESS_TOKEN="$(gcloud auth print-access-token)" uv run python -m skrooge.scraper scrape --output new.json
    # or: GCP_BILLING_API_KEY=... uv run python -m skrooge.scraper scrape --output new.json
    uv run python -m skrooge.scraper diff skrooge/instances.json new.json
    mv new.json skrooge/instances.json

If Google rejects your access token for not having a quota project, also set `GCP_QUOTA_PROJECT` to a project with the Cloud Billing API enabled. The scraper refuses to write output that fails validation, e.g. when a machine family has no prices. Machine type specs are hard-coded in `skrooge/machine_types.py`; add new machine types there.

## Releasing

Releases are made with Sentry's [Craft](https://github.com/getsentry/craft) and follow [Semantic Versioning](https://semver.org/). Anything that drops support for a Python version needs at least a minor version bump.

1. **Update the changelog.** Craft doesn't edit `CHANGELOG.md` for this project, so in a PR, rename the `## [Unreleased]` heading to `## [X.Y.Z] - YYYY-MM-DD`, add a new empty `## [Unreleased]` heading above it, and merge it to `main`. Make sure CI on `main` is green.
2. **Start the release.** In GitHub, go to **Actions → Release → Run workflow**, run it on `main`, and enter the new version, e.g. `1.1.0`. Enter an explicit version: `auto` and bump keywords like `minor` need a newer `minVersion` in `.craft.yml` than this project sets. Leave **force** empty unless you need to release despite an open issue labelled `release-blocker`.
3. **Craft prepares the release.** It creates a `release/X.Y.Z` branch from `main`, runs `scripts/bump-version.sh` (which uses `uv version` to update `pyproject.toml` and `uv.lock`), commits that as `release: X.Y.Z`, and opens a `publish: getsentry/skrooge@X.Y.Z` issue in [getsentry/publish](https://github.com/getsentry/publish).
4. **CI builds the package.** The push to `release/X.Y.Z` runs the [Publish Python Package](.github/workflows/publish.yml) workflow, which runs the tests and uploads the built sdist and wheel as an artifact for Craft. Wait for it to pass; the publish issue links to the check runs.
5. **Approve the release.** Add the `accepted` label to the publish issue. Craft then uploads the package to PyPI, tags the release and creates a GitHub release, and merges the release branch back into `main`. Nothing is published until the label is added, so to abandon a release, close the publish issue and delete the `release/X.Y.Z` branch.
6. **Check it.** Once PyPI has the new version, `uvx skrooge@X.Y.Z --version` should print it.
