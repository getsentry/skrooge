import difflib

import click

from .instances import instance_types


@click.group()
@click.version_option()
def cli():
    "A quick and dirty kubernetes cost estimator"


@cli.command(name="estimate")
@click.option(
    "-r",
    "--replicas",
    help="The number of replicas in the deployment",
    type=click.INT,
)
@click.option(
    "-c",
    "--cpu",
    help="The amount of CPU change",
    type=click.INT,
)
@click.option(
    "-m",
    "--mem",
    help="The amount of memory change in MiB",
    type=click.INT,
)
@click.option(
    "-i",
    "--instance",
    help="The instance type this deployment is running on",
)
def estimate(replicas, cpu, mem, instance):
    "Quick estimate of the cost or savings a kubernetes scale update will incur"
    click.echo(f"{replicas=}")
    click.echo(f"{cpu=}")
    click.echo(f"{mem=}")
    click.echo(f"{instance=}")

    if instance is not None:
        try:
            click.echo(f"{instance_types[instance]=}")
        except KeyError:
            close_matches = difflib.get_close_matches(instance, instance_types.keys())
            missing_instance_type_link = "https://github.com/getsentry/skrooge/issues/new?assignees=&labels=&projects=&template=BUG_REPORT.md"
            raise click.BadParameter(f"{instance} not found. Did you mean: {', '.join(close_matches)}\nMissing? {missing_instance_type_link}")


if __name__ == "__main__":
    cli()
