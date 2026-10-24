import json

import pytest
from click.testing import CliRunner

from skrooge import cli as cli_module
from skrooge import tui, utils
from skrooge.cli import cli
from skrooge.render import render

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
        "n2": {
            "me-central1": {"ondemand": {"cores": 0.03, "memory": 0.004}},
            # These add up to n2-standard-32's sud price
            "us-central1": {"sud": {"cores": 0.0252888, "memory": 0.0033896}},
        },
    },
}


@pytest.fixture
def instance_data(monkeypatch):
    # Each module that loads instances.json imports load_instance_types by name
    for module in (cli_module, tui, utils):
        monkeypatch.setattr(module, "load_instance_types", lambda: INSTANCE_DATA)
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
    assert "replicas=30" in result.output
    # logged from skrooge.utils
    assert "constrained_resource='cores'" in result.output
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


@pytest.mark.parametrize("region", ["us-cnetral1", "US-CNETRAL1"])
def test_invalid_region_suggests_similar_regions(region):
    # The --region choices come from the bundled data, which always has us-central1
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "estimate",
            *REQUIRED_ARGS,
            "--instance",
            "n2-standard-32",
            "--region",
            region,
        ],
    )
    assert result.exit_code == 2
    assert f"'{region}' isn't a region skrooge has pricing for." in result.output
    assert "Did you mean: us-central1" in result.output
    assert "List them with: skrooge regions" in result.output
    # Instead of Click's error, which lists every region
    assert "is not one of" not in result.output


def test_invalid_region_without_similar_regions():
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "estimate",
            *REQUIRED_ARGS,
            "--instance",
            "n2-standard-32",
            "--region",
            "mars",
        ],
    )
    assert result.exit_code == 2
    assert "'mars' isn't a region skrooge has pricing for." in result.output
    assert "Did you mean" not in result.output
    assert "List them with: skrooge regions" in result.output


def test_region_is_case_insensitive(instance_data):
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "estimate",
            *REQUIRED_ARGS,
            "--instance",
            "n2-standard-32",
            "--region",
            "US-CENTRAL1",
        ],
    )
    assert result.exit_code == 0
    assert "in us-central1" in result.output


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
    assert (
        "List them all with: skrooge regions --instance n1-highcpu-16 --cost-class sud"
        in result.output
    )


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


def test_memory_only_change(instance_data):
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
            0,
            "--mem",
            8192,
        ],
    )
    assert result.exit_code == 0
    assert "memory-constrained" in result.output
    assert "require 2 instances" in result.output


def test_tui_loads_workloads_and_prints_summary(instance_data, tmp_path, monkeypatch):
    path = tmp_path / "skrooge.json"
    path.write_text(
        json.dumps(
            {
                "workloads": [
                    {
                        "name": "web",
                        "replicas": 30,
                        "cpu": 2500,
                        "mem": 2024,
                        "instance": "n2-standard-32",
                    }
                ]
            }
        )
    )
    # Quit as soon as the TUI starts
    monkeypatch.setattr(tui.SkroogeApp, "run", lambda app: app.exit())

    result = CliRunner().invoke(cli, ["tui", str(path)])
    assert result.exit_code == 0
    assert "web" in result.output
    assert "$2,722" in result.output
    assert "Net change" in result.output


def test_tui_starts_with_a_workload_when_file_is_missing(tmp_path, monkeypatch):
    started = []
    monkeypatch.setattr(tui.SkroogeApp, "run", lambda app: started.append(app))

    result = CliRunner().invoke(cli, ["tui", str(tmp_path / "new.json")])
    assert result.exit_code == 0
    assert started[0].workloads == [tui.Workload()]
    assert started[0].path == tmp_path / "new.json"


def test_tui_rejects_invalid_workloads_file(tmp_path):
    path = tmp_path / "skrooge.json"
    path.write_text('{"workloads": [{"memory": 1024}]}')

    result = CliRunner().invoke(cli, ["tui", str(path)])
    assert result.exit_code == 2
    assert "unknown workload fields: memory" in result.output


WEB_ARGS = ["estimate", "-i", "n2-standard-32", "-r", "30", "-c", "2500", "-m", "2024"]


def test_bin_packed_estimate(instance_data):
    result = CliRunner().invoke(cli, [*WEB_ARGS, "--packing-efficiency", "80"])
    assert result.exit_code == 0
    assert (
        "Bin-packed in a cluster at 80% efficiency, this workload will cost $2.62/h (or $1914/m (or $22969/y)): $1731/m for cores and $183/m for memory."
        in result.output
    )


def test_bin_packed_estimate_in_json(instance_data):
    result = CliRunner().invoke(cli, [*WEB_ARGS, "--format", "json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["packing_efficiency"] == {"cores": 100, "memory": 100}
    assert data["resource_costs"]["total"]["monthly"] == 1532


def test_packing_efficiency_by_resource(instance_data):
    # -p sets both, and the per-resource options override it
    result = CliRunner().invoke(
        cli, [*WEB_ARGS, "-p", "80", "--mem-packing-efficiency", "50", "-f", "json"]
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["packing_efficiency"] == {"cores": 80, "memory": 50}
    # $1,385 / 0.8 and $147 / 0.5
    assert data["resource_costs"]["cores"]["monthly"] == 1731
    assert data["resource_costs"]["memory"]["monthly"] == 293

    result = CliRunner().invoke(cli, [*WEB_ARGS, "--cpu-packing-efficiency", "85"])
    assert "in a cluster at 85% CPU and 100% memory efficiency" in result.output


def test_no_bin_packed_estimate_when_pricing_cant_be_split(instance_data):
    # n1-highcpu-16 has no recorded resource prices, and is the only n1 type to fit
    result = CliRunner().invoke(
        cli, ["estimate", *REQUIRED_ARGS, "--instance", "n1-highcpu-16"]
    )
    assert result.exit_code == 0
    assert "skrooge can't split n1-highcpu-16 pricing into cores and memory" in (
        result.output
    )


def test_packing_efficiency_must_be_a_percentage():
    result = CliRunner().invoke(cli, [*WEB_ARGS, "--packing-efficiency", "0"])
    assert result.exit_code == 2
    assert "0 is not in the range 1<=x<=100" in result.output


def test_tui_loads_settings(tmp_path, monkeypatch):
    path = tmp_path / "skrooge.json"
    path.write_text(
        json.dumps(
            {
                "cost_model": "bin-packed",
                "cpu_packing_efficiency": 75,
                "mem_packing_efficiency": 60,
                "workloads": [],
            }
        )
    )
    started = []
    monkeypatch.setattr(tui.SkroogeApp, "run", lambda app: started.append(app))

    result = CliRunner().invoke(cli, ["tui", str(path)])
    assert result.exit_code == 0
    assert started[0].settings == tui.Settings("bin-packed", "75", "60")


def test_render_rejects_unknown_formats():
    with pytest.raises(ValueError, match="Unknown format: yaml"):
        render("yaml", {})


def test_estimate_help_leaves_out_the_region_choices():
    runner = CliRunner()
    result = runner.invoke(cli, ["estimate", "--help"])
    assert result.exit_code == 0
    assert "--region REGION" in result.output
    assert "us-central1|" not in result.output


@pytest.mark.parametrize(
    ("args", "regions"),
    [
        ([], ["europe-west2", "europe-west10", "us-central1", "us-east4", "us-east5"]),
        (["--instance", "n1-highcpu-16"], ["us-central1", "us-east4", "us-east5"]),
        (["--cost-class", "cud-1y"], ["us-central1", "us-east5"]),
        (
            ["--instance", "n1-highcpu-16", "--cost-class", "SUD"],
            ["us-central1", "us-east4"],
        ),
    ],
)
def test_regions(instance_data, args, regions):
    runner = CliRunner()
    result = runner.invoke(cli, ["regions", *args])
    assert result.exit_code == 0
    assert result.output.splitlines() == regions


def test_regions_with_no_match(instance_data):
    runner = CliRunner()
    result = runner.invoke(
        cli, ["regions", "--instance", "n1-highcpu-16", "--cost-class", "preemptible"]
    )
    assert result.exit_code == 1
    assert "No region has preemptible pricing for n1-highcpu-16." in result.output


def test_regions_for_invalid_instance_type_provides_similar_instances(instance_data):
    runner = CliRunner()
    result = runner.invoke(cli, ["regions", "--instance", "n2-standard-30"])
    assert result.exit_code == 2
    assert "n2-standard-30 not found. Did you mean: n2-standard-32" in result.output


def test_invalid_instance_family_provides_similar_families(instance_data):
    runner = CliRunner()
    result = runner.invoke(cli, ["regions", "--instance", "n9-standard-8"])
    assert result.exit_code == 2
    assert "n9 instance family not found. Did you mean:" in result.output
    assert "n1" in result.output
    assert "n2" in result.output
