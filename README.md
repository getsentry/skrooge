# skrooge

[![PyPI](https://img.shields.io/pypi/v/skrooge.svg)](https://pypi.org/project/skrooge/)
[![Changelog](https://img.shields.io/github/v/release/getsentry/skrooge?include_prereleases&label=changelog)](https://github.com/getsentry/skrooge/releases)
[![Tests](https://github.com/getsentry/skrooge/actions/workflows/python-package.yml/badge.svg)](https://github.com/getsentry/skrooge/actions/workflows/python-package.yml)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](https://github.com/getsentry/skrooge/blob/main/LICENSE)

A quick and dirty kubernetes cost estimator

![OIG 0uCanRKKeLq7XwJysZQ3](https://github.com/getsentry/skrooge/assets/67560/8ba2d274-4281-43a0-ad75-f0838e29e5f4)
*Ebenezer scrooge standing at the helm of a ship, pencil sketch*


## Idea

I've been manually calculating how much scaling kubernetes deployments up or down will cost (or save!).
It's a bit of grunt work every time pulling together our instance types, figuring out if the deployment is cpu-bound or memory-bound, and working out the cost.
Instead we could have a CLI tool (or potentially automated during CI down the road) that could calculate these numbers for us.

Previous example (in english):

It would be nice to have a CLI tool which could do these calculations for us (and integrate with GCP pricing / instance APIs to get instance shapes and costs automatically)

```
Pod size: 2 cpu, 3GB RAM
Previous deployment: 32 cpu, 48GB RAM
New deployment: 64 cpu, 96GB RAM
Running on c2-standard-30 which have 30 cpu, 120GiB RAM, and cost $914/month
Up to 2 new instances to support +32 CPU, cost $1828 / month ($21,936 / year)
```

How a CLI tool could work:

```bash
$ kubecost --cpu 32 --mem 48 --instance c2-standard-30
c2-standard-30: 30 cpu, 120GiB RAM, $914/month
Limiting factor: CPU (ceil(32/30) = 2)
Cost: $1828 / month ($21,936 / year)
```

## Installation

skrooge requires Python 3.11 or newer. The quickest way to use it is to run it with [`uvx`](https://docs.astral.sh/uv/guides/tools/), which fetches and runs the latest release without installing it:

    uvx --from skrooge skrooge --help

To install it as a standalone tool instead, use `uv`:

    uv tool install skrooge

Or with `pipx` or `pip`:

    pipx install skrooge
    pip install skrooge

## Usage

Estimate the cost of adding 5.81 cores and 9950MiB of memory to each of 1000 replicas running on `n2-highcpu-64` nodes:

    $ uvx --from skrooge skrooge estimate --replicas 1000 --cpu 5810 --mem 9950 --instance n2-highcpu-64
    This workload is running on n2-highcpu-64 instances in us-central1 with 64 cores and 64GiB of memory.
    This workload will require 5810.0 cores and 9716.796875 GiB of memory. This workload is memory-constrained.
    This workload will require 152 instances, costing $278.98/h (or $203658/m (or $2443898/y)) at sud rates.

Use `--region`, `--cost-class`, and `--format json` to change the region, pricing tier, and output format:

    uvx --from skrooge skrooge estimate --replicas 1000 --cpu 5810 --mem 9950 --instance n2-highcpu-64 --region europe-west1 --cost-class cud-1y --format json

If you installed skrooge, drop the `uvx --from skrooge` prefix and run `skrooge` directly (or `python -m skrooge`).

For help, run:

    uvx --from skrooge skrooge --help
    uvx --from skrooge skrooge estimate --help

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
