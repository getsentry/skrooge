import difflib

import click

from .instances import instance_types
from .utils import determine_constrained_resource, determine_instance_count_required


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
    help="The amount of CPU change in milli-cores",
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
    required=True,
)
def estimate(replicas, cpu, mem, instance):
    "Quick estimate of the cost or savings a kubernetes scale update will incur"
    click.echo(f"{replicas=}")
    click.echo(f"{cpu=}m")
    click.echo(f"{mem=}MiB")
    click.echo(f"{instance=}")

    try:
        instance_data = instance_types[instance]
    except KeyError:
        close_matches = difflib.get_close_matches(instance, instance_types.keys())
        missing_instance_type_link = "https://github.com/getsentry/skrooge/issues/new?assignees=&labels=&projects=&template=BUG_REPORT.md"
        raise click.BadParameter(f"{instance} not found. Did you mean: {', '.join(close_matches)}\nMissing? {missing_instance_type_link}")

    click.echo(f"{instance_data=}")

    delta_cpu = replicas * cpu
    delta_mem = replicas * mem

    click.echo(f"{delta_cpu=}m {delta_mem=}MiB")

    constrained_resource = determine_constrained_resource(instance_data, cpu, mem)
    click.echo(f"{constrained_resource=}")

    if constrained_resource == "cpu":
        resource_requirement = delta_cpu
    else:
        resource_requirement = delta_mem

    required_instance_count = determine_instance_count_required(instance_data, constrained_resource, resource_requirement)
    click.echo(f"{required_instance_count=}")

if __name__ == "__main__":
    cli()
