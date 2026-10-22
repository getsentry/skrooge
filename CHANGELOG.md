# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- `--verbosity` now also shows log output from the cost calculation functions
- Correct the `--format` help text

### Changed

- Require Python 3.11 or newer; Python 3.8, 3.9, and 3.10 are no longer supported
- Build with `uv_build` and manage development with `uv`

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

[unreleased]: https://github.com/getsentry/skrooge/compare/1.0.0...HEAD
[1.0.2]: https://github.com/getsentry/skrooge/compare/1.0.1...1.0.2
[1.0.1]: https://github.com/getsentry/skrooge/compare/1.0.0...1.0.1
[1.0.0]: https://github.com/getsentry/skrooge/compare/0.0.0...1.0.0
[0.0.0]: https://github.com/getsentry/skrooge/releases/tag/0.0.0
