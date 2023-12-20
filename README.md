# skrooge

[![PyPI](https://img.shields.io/pypi/v/skrooge.svg)](https://pypi.org/project/skrooge/)
[![Changelog](https://img.shields.io/github/v/release/mwarkentin/skrooge?include_prereleases&label=changelog)](https://github.com/mwarkentin/skrooge/releases)
[![Tests](https://github.com/mwarkentin/skrooge/workflows/Test/badge.svg)](https://github.com/mwarkentin/skrooge/actions?query=workflow%3ATest)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](https://github.com/mwarkentin/skrooge/blob/master/LICENSE)

A quick and dirty kubernetes cost estimator

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

Install this tool using `pip`:

    pip install skrooge

## Usage

For help, run:

    skrooge --help

You can also use:

    python -m skrooge --help

## Development

To contribute to this tool, first checkout the code. Then create a new virtual environment:

    cd skrooge
    python -m venv venv
    source venv/bin/activate

Now install the dependencies and test dependencies:

    pip install -e '.[test]'

To run the tests:

    pytest
