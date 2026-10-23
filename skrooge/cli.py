import difflib
import functools
import json
import logging
import re
from importlib.resources import files

import click
import click_log

from .render import render
from .utils import (
    calculate_cost,
    determine_constrained_resource,
    determine_instance_count_required,
)

logger = logging.getLogger(__name__)
# Configure the package logger so --verbosity also covers skrooge.utils
package_logger = logging.getLogger("skrooge")
click_log.basic_config(package_logger)

COST_CLASSES = ["sud", "ondemand", "preemptible", "cud-1y", "cud-3y"]
MISSING_INSTANCE_TYPE_LINK = "https://github.com/getsentry/skrooge/issues/new?assignees=&labels=&projects=&template=BUG_REPORT.md"


@functools.cache
def load_instance_types():
    return json.loads(
        files("skrooge").joinpath("instances.json").read_text(encoding="utf-8")
    )


def available_regions(cost_class=None, instance_data=None):
    "Regions with pricing, optionally only in one cost class or for one instance type"
    if instance_data is None:
        all_instance_data = [
            data
            for family in load_instance_types().values()
            for data in family.values()
            if data
        ]
    else:
        all_instance_data = [instance_data]
    # Skip aggregate pricing keys such as "us" or "asia-east"; GCP regions end in a digit
    return sorted(
        {
            region
            for data in all_instance_data
            for region, prices in data.get("regions", {}).items()
            if region[-1].isdigit() and (cost_class is None or cost_class in prices)
        },
        # Natural sort, so europe-west2 comes before europe-west10
        key=lambda region: [
            int(part) if part.isdigit() else part for part in re.split(r"(\d+)", region)
        ],
    )


def find_instance_type(instance):
    "Look up an instance type's data, suggesting similar ones if it doesn't exist"
    instance_family = instance.split("-")[0]
    instance_types = load_instance_types()

    try:
        return instance_types[instance_family][instance]
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
                f"{instance_family} instance family not found. Did you mean: {', '.join(close_matches)}\nMissing an instance family that exists? {MISSING_INSTANCE_TYPE_LINK}"
            ) from None
        raise click.BadParameter(
            f"{instance} not found. Did you mean: {', '.join(close_matches)}\nMissing an instance type that exists? {MISSING_INSTANCE_TYPE_LINK}"
        ) from None


@click.group()
@click.version_option()
def cli():
    "A quick and dirty kubernetes cost estimator"


@cli.command(name="estimate")
@click_log.simple_verbosity_option(package_logger, default="ERROR")
@click.option(
    "-r",
    "--replicas",
    help="The number of replicas in the deployment",
    type=click.IntRange(min=1),
    required=True,
)
@click.option(
    "-c",
    "--cpu",
    help="The amount of CPU change in milli-cores",
    type=click.INT,
    required=True,
)
@click.option(
    "-m",
    "--mem",
    help="The amount of memory change in MiB",
    type=click.INT,
    required=True,
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
    type=click.Choice(COST_CLASSES, case_sensitive=False),
    default="sud",
)
@click.option(
    "--region",
    help="The region to use for cost calculation. Default: us-central1. List them with: skrooge regions",
    type=click.Choice(available_regions(), case_sensitive=False),
    # The choices are long, so leave them out of --help
    metavar="REGION",
    default="us-central1",
)
@click.option(
    "-f",
    "--format",
    help="The output format. Default: english",
    type=click.Choice(["english", "json"], case_sensitive=False),
    default="english",
)
def estimate(replicas, cpu, mem, instance, cost_class, region, format):
    "Quick estimate of the cost or savings a kubernetes scale update will incur"
    logger.info(f"{replicas=}")
    logger.info(f"{cpu=}m")
    logger.info(f"{mem=}MiB")
    logger.info(f"{instance=}")

    instance_family = instance.split("-")[0]
    instance_data = find_instance_type(instance)

    if not all(
        isinstance(instance_data["specs"][resource], (int, float))
        for resource in ("cores", "memory")
    ):
        raise click.BadParameter(
            f"{instance} is a shared-core instance type without a fixed number of cores, so skrooge can't estimate it."
        )

    if cpu == 0 and mem == 0:
        raise click.BadParameter("--cpu and --mem can't both be 0.")

    prices = instance_data["regions"].get(region, {})
    if cost_class not in prices:
        regions_with_pricing = available_regions(cost_class, instance_data)
        suggestions = []
        if prices:
            suggestions.append(
                f"Cost classes available for {instance} in {region}: {', '.join(c for c in COST_CLASSES if c in prices)}"
            )
        close_matches = difflib.get_close_matches(region, regions_with_pricing)
        if close_matches:
            suggestions.append(
                f"Similar regions with {cost_class} pricing for {instance}: {', '.join(close_matches)}"
            )
        if regions_with_pricing:
            suggestions.append(
                f"List them all with: skrooge regions --instance {instance} --cost-class {cost_class}"
            )
        raise click.BadParameter(
            "\n".join(
                [f"No {cost_class} pricing for {instance} in {region}.", *suggestions]
            )
        )

    delta_cpu = replicas * abs(cpu)
    delta_mem = replicas * abs(mem)

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
        instance_data,
        required_instance_count,
        cost_class=cost_class,
        region=region,
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
        "region": region,
    }

    logger.info(f"{data=}")

    render(format=format, data=data)


@cli.command(name="regions")
@click.option(
    "-i",
    "--instance",
    help="Only list regions with pricing for this instance type",
)
@click.option(
    "--cost-class",
    help="Only list regions with pricing in this cost class",
    type=click.Choice(COST_CLASSES, case_sensitive=False),
)
def regions(instance, cost_class):
    "List the regions skrooge has prices for"
    instance_data = find_instance_type(instance) if instance else None
    matching_regions = available_regions(cost_class, instance_data)
    if not matching_regions:
        raise click.ClickException(
            f"No region has {cost_class or 'any'} pricing for {instance or 'any instance type'}."
        )
    click.echo("\n".join(matching_regions))


if __name__ == "__main__":
    cli()
