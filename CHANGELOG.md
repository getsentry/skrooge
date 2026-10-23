# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `skrooge tui`, an interactive terminal UI that updates estimates live as you edit inputs, handles several workloads at once with a net total, and saves them to a JSON file
- Bin-packed estimates, which charge a workload for just the CPU and memory it requests at per-vCPU and per-GiB prices, for large shared clusters. `estimate` prints one alongside the whole-node estimate (and adds `packing_efficiency`, `resource_prices`, and `resource_costs` to `--format json`), and the TUI can switch between the two
- `--packing-efficiency` (`-p`), and a matching TUI setting, to account for how full a cluster's nodes are in bin-packed estimates
- `c4d`, `n4d` and `n4a` machine types, once `instances.json` is next regenerated

### Changed

- The price scraper now reads prices from GCP's Cloud Billing Catalog API, as the pricing calculator price list it used is gone. A daily workflow opens a pull request when prices change, with a report of what changed.

## [1.1.0] - 2026-10-22

### Fixed

- `estimate` no longer crashes with a traceback when:
  - `--replicas`, `--cpu`, or `--mem` is missing (they're now required, and `--replicas` must be at least 1)
  - the chosen region or cost class has no pricing for the instance type; the error lists the cost classes and similar regions that do
  - `--cpu` or `--mem` is 0, or the instance type is a shared-core type (`f1-micro`, `g1-small`)
- `--region` choices now come from the bundled pricing data, which removes `us-central2` (no pricing) and adds `africa-south1`, `europe-west10`, `europe-west12`, `me-central1`, `me-central2`, and `me-west1`
- Treat negative `--cpu` and `--mem` values (for a scale-down) as the size of the change instead of producing negative results
- `--verbosity` now also shows log output from the cost calculation functions
- Correct the `--format` help text

### Changed

- Require Python 3.11 or newer; Python 3.8, 3.9, and 3.10 are no longer supported
- Build with `uv_build` and manage development with `uv`
- Project links on PyPI now point to `getsentry/skrooge`

### Removed

- Remove the `lint`, `test`, and `scrape` extras in favour of `dev` and `scrape` dependency groups

## [1.0.2] - 2024-01-26

### Fixed

- Fix reference to `data.costs.class` for english render

## [1.0.1] - 2024-01-26

### Fixed

- Include `skrooge/instances.json` in setuptools package-data for use after pip install

## [1.0.0] - 2024-01-26

### Added

- Initial release.

## [0.0.0] - 2023-12-20

### Added

- Initial commit.

[unreleased]: https://github.com/getsentry/skrooge/compare/1.1.0...HEAD
[1.1.0]: https://github.com/getsentry/skrooge/releases/tag/1.1.0
[1.0.2]: https://github.com/getsentry/skrooge/compare/1.0.1...1.0.2
[1.0.1]: https://github.com/getsentry/skrooge/compare/1.0.0...1.0.1
[1.0.0]: https://github.com/getsentry/skrooge/compare/0.0.0...1.0.0
[0.0.0]: https://github.com/getsentry/skrooge/releases/tag/0.0.0
