import difflib
import json
import logging
import os

import click
import click_log

from .render import render
from .utils import (
    calculate_cost,
    determine_constrained_resource,
    determine_instance_count_required,
)

logger = logging.getLogger(__name__)
click_log.basic_config(logger)


@click.group()
@click.version_option()
def cli():
    "A quick and dirty kubernetes cost estimator"


@cli.command(name="estimate")
@click_log.simple_verbosity_option(logger, default="ERROR")
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
@click.option(
    "--cost-class",
    help="The type of cost to calculate. Default: sud",
    type=click.Choice(
        ["sud", "ondemand", "preemptible", "cud-1y", "cud-3y"], case_sensitive=False
    ),
    default="sud",
)
@click.option(
    "-f",
    "--format",
    help="The instance type this deployment is running on",
    type=click.Choice(["english", "json"], case_sensitive=False),
    default="english",
)
def estimate(replicas, cpu, mem, instance, cost_class, format):
    "Quick estimate of the cost or savings a kubernetes scale update will incur"
    logger.info(f"{replicas=}")
    logger.info(f"{cpu=}m")
    logger.info(f"{mem=}MiB")
    logger.info(f"{instance=}")

    instance_family = instance.split("-")[0]

    # Get the absolute path to the directory of the script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    instance_data_path = os.path.join(script_dir, "instances.json")

    with open(instance_data_path, "r") as file:
        instance_types = json.load(file)

    missing_instance_type_link = "https://github.com/getsentry/skrooge/issues/new?assignees=&labels=&projects=&template=BUG_REPORT.md"

    try:
        instance_data = instance_types[instance_family][instance]
    except KeyError:
        try:
            close_matches = difflib.get_close_matches(
                instance, instance_types[instance_family].keys()
            )
        except KeyError:
            logger.info(f"{instance_family}, {instance_types.keys()}")
            close_matches = difflib.get_close_matches(
                instance_family, instance_types.keys(), cutoff=0.4
            )
            raise click.BadParameter(
                f"{instance_family} instance family not found. Did you mean: {', '.join(close_matches)}\nMissing an instance family that exists? {missing_instance_type_link}"
            )
        raise click.BadParameter(
            f"{instance} not found. Did you mean: {', '.join(close_matches)}\nMissing an instance type that exists? {missing_instance_type_link}"
        )

    delta_cpu = replicas * cpu
    delta_mem = replicas * mem

    logger.info(f"{delta_cpu=}m {delta_mem=}MiB")

    constrained_resource = determine_constrained_resource(instance_data, cpu, mem)
    logger.info(f"{constrained_resource=}")

    if constrained_resource == "cores":
        resource_requirement = delta_cpu
    else:
        resource_requirement = delta_mem

    required_instance_count = determine_instance_count_required(
        instance_data, constrained_resource, resource_requirement
    )
    logger.info(f"{required_instance_count=}")

    costs = calculate_cost(
        instance_data, required_instance_count, cost_class=cost_class
    )
    logger.info(costs)

    data = {
        "replicas": replicas,
        "cpu": cpu,
        "mem": mem,
        "delta_cpu": delta_cpu,
        "delta_mem": delta_mem,
        "constrained_resource": constrained_resource,
        "resource_requirement": resource_requirement,
        "required_instance_count": required_instance_count,
        "instance": instance,
        "instance_family": instance_family,
        "instance_specs": instance_data["specs"],
        "costs": costs,
    }

    logger.info(f"{data=}")

    render(format=format, data=data)


if __name__ == "__main__":
    cli()
