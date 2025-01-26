from click.testing import CliRunner
from skrooge.cli import cli


def test_version():
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert result.output.startswith("cli, version ")


def test_invalid_instance_type_provides_similar_instances():
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["estimate", "--instance", "c2-standard-7"])
        assert result.exit_code == 2
        assert (
            "Error: Invalid value: c2-standard-7 not found. Did you mean:"
            in result.output
        )


def test_invalid_instance_type_provides_github_bug_report_link():
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["estimate", "--instance", "c2-standard-7"])
        assert result.exit_code == 2
        assert (
            "https://github.com/getsentry/skrooge/issues/new?assignees=&labels=&projects=&template=BUG_REPORT.md"
            in result.output
        )


def test_treat_negative_cpu_and_mem_values_as_absolute():
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["estimate", "--instance", "n2-standard-32", "--replicas", 30, "--cpu", -2500, "--mem", -2024])
        assert result.exit_code == 0

        # whitespace prefix to check non-negative
        assert " 75.0" in result.output
        assert " 59.296875" in result.output
        assert "cores-constrained" in result.output
        assert "require 3 instances" in result.output
        assert "$3.73/h" in result.output
        assert "$2722/m" in result.output
        assert "$32669/y" in result.output
