# skrooge

[![PyPI](https://img.shields.io/pypi/v/skrooge.svg)](https://pypi.org/project/skrooge/)
[![Changelog](https://img.shields.io/github/v/release/getsentry/skrooge?include_prereleases&label=changelog)](https://github.com/getsentry/skrooge/releases)
[![Tests](https://github.com/getsentry/skrooge/workflows/Test/badge.svg)](https://github.com/getsentry/skrooge/actions?query=workflow%3ATest)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](https://github.com/getsentry/skrooge/blob/master/LICENSE)

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

Install this tool using `pip`:

    pip install skrooge

## Usage

Run `skrooge --help` to see the available commands:

```text
Usage: skrooge [OPTIONS] COMMAND [ARGS]...

  A quick and dirty kubernetes cost estimator

Options:
  --version  Show the version and exit.
  --help     Show this message and exit.

Commands:
  estimate  Quick estimate of the cost or savings a kubernetes scale...
```

The `estimate` command accepts the following options:

```text
Usage: skrooge estimate [OPTIONS]

  Quick estimate of the cost or savings a kubernetes scale update will incur

Options:
  -v, --verbosity LVL             Either CRITICAL, ERROR, WARNING, INFO or
                                  DEBUG
  -r, --replicas INTEGER          The number of replicas in the deployment
  -c, --cpu INTEGER               The amount of CPU change in milli-cores
  -m, --mem INTEGER               The amount of memory change in MiB
  -i, --instance TEXT             The instance type this deployment is running
                                  on  [required]
  --cost-class [sud|ondemand|preemptible|cud-1y|cud-3y]
                                  The type of cost to calculate. Default: sud
  --region [asia-east1|asia-east2|asia-northeast1|asia-northeast2|asia-northeast3|asia-south1|asia-south2|asia-southeast1|asia-southeast2|australia-southeast1|australia-southeast2|europe-central2|europe-north1|europe-southwest1|europe-west1|europe-west2|europe-west3|europe-west4|europe-west6|europe-west8|europe-west9|northamerica-northeast1|northamerica-northeast2|southamerica-east1|southamerica-west1|us-central1|us-central2|us-east1|us-east4|us-east5|us-south1|us-west1|us-west2|us-west3|us-west4]
                                  The region to use for cost calculation.
                                  Default: us-central1
  -f, --format [english|json]     The instance type this deployment is running
                                  on
  --help                          Show this message and exit.
```

You can also invoke the CLI as a Python module, for example
`python -m skrooge --help`.

## Development

To contribute to this tool, first checkout the code. Then create a new virtual environment:

    cd skrooge
    python -m venv venv
    source venv/bin/activate

Now install the dependencies, test dependencies, and GCP cost scraping dependencies:

    pip install -e '.[lint,scrape,test]'

To run the tests:

    pytest

To update the instances.json file:

    python3 skrooge/scraper.py > skrooge/instances.json
