import difflib
import json

import click

from .utils import calculate_cost, determine_constrained_resource, determine_instance_count_required


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

    instance_family = instance.split("-")[0]

    instance_data_path = 'skrooge/instances.json'

    with open(instance_data_path, 'r') as file:
        instance_types = json.load(file)

    missing_instance_type_link = "https://github.com/getsentry/skrooge/issues/new?assignees=&labels=&projects=&template=BUG_REPORT.md"

    try:
        instance_data = instance_types[instance_family][instance]
    except KeyError:
        try:
            close_matches = difflib.get_close_matches(instance, instance_types[instance_family].keys())
        except KeyError:
            click.echo(f"{instance_family}, {instance_types.keys()}")
            close_matches = difflib.get_close_matches(instance_family, instance_types.keys(), cutoff=0.4)
            raise click.BadParameter(f"{instance_family} instance family not found. Did you mean: {', '.join(close_matches)}\nMissing an instance family that exists? {missing_instance_type_link}")
        raise click.BadParameter(f"{instance} not found. Did you mean: {', '.join(close_matches)}\nMissing an instance type that exists? {missing_instance_type_link}")

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

    costs = calculate_cost(instance_data, required_instance_count)
    click.echo(costs)

if __name__ == "__main__":
    cli()
