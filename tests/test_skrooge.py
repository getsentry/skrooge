import json

from click.testing import CliRunner

from skrooge import tui
from skrooge.cli import cli


def test_version():
    runner = CliRunner()
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert result.output.startswith("cli, version ")


def test_invalid_instance_type_provides_similar_instances():
    runner = CliRunner()
    result = runner.invoke(cli, ["estimate", "--instance", "c2-standard-7"])
    assert result.exit_code == 2
    assert (
        "Error: Invalid value: c2-standard-7 not found. Did you mean:" in result.output
    )


def test_invalid_instance_type_provides_github_bug_report_link():
    runner = CliRunner()
    result = runner.invoke(cli, ["estimate", "--instance", "c2-standard-7"])
    assert result.exit_code == 2
    assert (
        "https://github.com/getsentry/skrooge/issues/new?assignees=&labels=&projects=&template=BUG_REPORT.md"
        in result.output
    )


def test_treat_negative_cpu_and_mem_values_as_absolute():
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


def test_verbosity_includes_calculation_logs():
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


def test_missing_pricing_is_reported():
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "estimate",
            "--instance",
            "m3-ultramem-32",
            "--replicas",
            1,
            "--cpu",
            1000,
            "--mem",
            1024,
            "--cost-class",
            "preemptible",
        ],
    )
    assert result.exit_code == 2
    assert "No preemptible pricing for m3-ultramem-32 in us-central1." in result.output


def test_memory_only_change():
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


def test_tui_loads_workloads_and_prints_summary(tmp_path, monkeypatch):
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
