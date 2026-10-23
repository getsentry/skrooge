import pytest
from click.testing import CliRunner

from skrooge import cli as cli_module
from skrooge.cli import cli

REQUIRED_ARGS = ["--replicas", "30", "--cpu", "2500", "--mem", "2024"]

# A fixed copy of part of instances.json, so tests that check prices don't break when the
# bundled data is updated
INSTANCE_DATA = {
    "n2": {
        "n2-standard-32": {
            "regions": {
                "us": {"ondemand": 1.55389},
                "us-central1": {
                    "ondemand": 1.55389,
                    "sud": 1.24311,
                    "preemptible": 0.40192,
                    "cud-1y": 0.97891,
                    "cud-3y": 0.6993,
                },
                "europe-west10": {"ondemand": 1.8},
                "europe-west2": {"ondemand": 1.8},
            },
            "specs": {"cores": 32, "memory": 128},
        },
    },
    "n1": {
        "n1-highcpu-16": {
            "regions": {
                "us-central1": {"ondemand": 0.5672, "sud": 0.39704},
                "us-east4": {"ondemand": 0.5672, "sud": 0.39704},
                "us-east5": {"cud-1y": 0.35707, "cud-3y": 0.25506},
            },
            "specs": {"cores": 16, "memory": 14.4},
        },
    },
    "resource_prices": {
        "n2": {"me-central1": {"ondemand": {"cores": 0.03, "memory": 0.004}}},
    },
}


@pytest.fixture
def instance_data(monkeypatch):
    monkeypatch.setattr(cli_module, "load_instance_types", lambda: INSTANCE_DATA)
    return INSTANCE_DATA


def test_version():
    runner = CliRunner()
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert result.output.startswith("cli, version ")


def test_invalid_instance_type_provides_similar_instances():
    runner = CliRunner()
    result = runner.invoke(
        cli, ["estimate", *REQUIRED_ARGS, "--instance", "c2-standard-7"]
    )
    assert result.exit_code == 2
    assert (
        "Error: Invalid value: c2-standard-7 not found. Did you mean:" in result.output
    )


def test_invalid_instance_type_provides_github_bug_report_link():
    runner = CliRunner()
    result = runner.invoke(
        cli, ["estimate", *REQUIRED_ARGS, "--instance", "c2-standard-7"]
    )
    assert result.exit_code == 2
    assert (
        "https://github.com/getsentry/skrooge/issues/new?assignees=&labels=&projects=&template=BUG_REPORT.md"
        in result.output
    )


def test_treat_negative_cpu_and_mem_values_as_absolute(instance_data):
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "estimate",
            "--instance",
            "n2-standard-32",
            "--replicas",
            30,
            "--cpu",
            -2500,
            "--mem",
            -2024,
        ],
    )
    assert result.exit_code == 0

    # whitespace prefix to check non-negative
    assert " 75.0" in result.output
    assert " 59.296875" in result.output
    assert "cores-constrained" in result.output
    assert "require 3 instances" in result.output
    assert "$3.73/h" in result.output
    assert "$2722/m" in result.output
    assert "$32669/y" in result.output


def test_verbosity_includes_calculation_logs(instance_data):
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "estimate",
            "--instance",
            "n2-standard-32",
            "--replicas",
            30,
            "--cpu",
            2500,
            "--mem",
            2024,
            "--verbosity",
            "INFO",
        ],
    )
    assert result.exit_code == 0
    # logged from skrooge.cli
    assert "constrained_resource='cores'" in result.output
    # logged from skrooge.utils
    assert "Calculating constrained resource" in result.output


def test_missing_required_options():
    runner = CliRunner()
    result = runner.invoke(cli, ["estimate", "--instance", "n2-standard-32"])
    assert result.exit_code == 2
    assert "Missing option '-r' / '--replicas'" in result.output


def test_replicas_must_be_positive():
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "estimate",
            "--instance",
            "n2-standard-32",
            "--replicas",
            "0",
            "--cpu",
            "2500",
            "--mem",
            "2024",
        ],
    )
    assert result.exit_code == 2
    assert "0 is not in the range x>=1" in result.output


def test_region_without_pricing_data_is_not_offered():
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "estimate",
            *REQUIRED_ARGS,
            "--instance",
            "n2-standard-32",
            "--region",
            "us-central2",
        ],
    )
    assert result.exit_code == 2
    assert "Invalid value for '--region'" in result.output


def test_regions_are_read_from_instance_data(instance_data):
    # Skips aggregate regions like "us" and the resource_prices key, in natural order
    assert cli_module.available_regions() == [
        "europe-west2",
        "europe-west10",
        "us-central1",
        "us-east4",
        "us-east5",
    ]


def test_bundled_data_offers_the_default_region():
    assert "us-central1" in cli_module.available_regions()


def test_missing_pricing_suggests_alternatives(instance_data):
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "estimate",
            *REQUIRED_ARGS,
            "--instance",
            "n1-highcpu-16",
            "--region",
            "us-east5",
        ],
    )
    assert result.exit_code == 2
    assert "No sud pricing for n1-highcpu-16 in us-east5." in result.output
    assert "Cost classes available for n1-highcpu-16 in us-east5: cud-1y" in (
        result.output
    )
    assert "Similar regions with sud pricing for n1-highcpu-16:" in result.output


def test_shared_core_instance_type_is_rejected():
    runner = CliRunner()
    result = runner.invoke(cli, ["estimate", *REQUIRED_ARGS, "--instance", "f1-micro"])
    assert result.exit_code == 2
    assert "f1-micro is a shared-core instance type" in result.output


def test_zero_cpu_and_mem_is_rejected():
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "estimate",
            "--instance",
            "n2-standard-32",
            "--replicas",
            "30",
            "--cpu",
            "0",
            "--mem",
            "0",
        ],
    )
    assert result.exit_code == 2
    assert "--cpu and --mem can't both be 0" in result.output
