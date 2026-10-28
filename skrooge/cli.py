import difflib
import logging
from pathlib import Path

import click
import click_log

from .render import render
from .utils import (
    COST_CLASSES,
    EstimateError,
    available_regions,
    calculate_estimate,
    find_instance_data,
    load_instance_types,
)

logger = logging.getLogger(__name__)
# Configure the package logger so --verbosity also covers skrooge.utils
package_logger = logging.getLogger("skrooge")
click_log.basic_config(package_logger)


class RegionChoice(click.Choice):
    "A choice of region whose error suggests similar regions instead of listing them all"

    def get_invalid_choice_message(self, value, ctx):
        close_matches = difflib.get_close_matches(str(value).lower(), self.choices)
        suggestion = (
            f" Did you mean: {', '.join(close_matches)}" if close_matches else ""
        )
        return f"{value!r} isn't a region skrooge has pricing for.{suggestion}\nList them with: skrooge regions"


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
    type=RegionChoice(available_regions(), case_sensitive=False),
    # The choices are long, so leave them out of --help
    metavar="REGION",
    default="us-central1",
)
@click.option(
    "-p",
    "--packing-efficiency",
    help="For the bin-packed estimate, the percentage of the cluster's CPU and memory that pods request on average. Default: 100",
    type=click.IntRange(1, 100),
    default=100,
)
@click.option(
    "--cpu-packing-efficiency",
    help="Like --packing-efficiency, for CPU only. Default: --packing-efficiency",
    type=click.IntRange(1, 100),
)
@click.option(
    "--mem-packing-efficiency",
    help="Like --packing-efficiency, for memory only. Default: --packing-efficiency",
    type=click.IntRange(1, 100),
)
@click.option(
    "-f",
    "--format",
    help="The output format. Default: english",
    type=click.Choice(["english", "json", "scrooge", "mcduck"], case_sensitive=False),
    default="english",
)
def estimate(
    replicas,
    cpu,
    mem,
    instance,
    cost_class,
    region,
    packing_efficiency,
    cpu_packing_efficiency,
    mem_packing_efficiency,
    format,
):
    "Quick estimate of the cost or savings a kubernetes scale update will incur"
    logger.info(f"{replicas=}")
    logger.info(f"{cpu=}m")
    logger.info(f"{mem=}MiB")
    logger.info(f"{instance=}")

    if cpu == 0 and mem == 0:
        raise click.BadParameter("--cpu and --mem can't both be 0.")

    try:
        data = calculate_estimate(
            load_instance_types(),
            instance,
            replicas,
            cpu,
            mem,
            cost_class=cost_class,
            region=region,
            packing_efficiency={
                "cores": cpu_packing_efficiency or packing_efficiency,
                "memory": mem_packing_efficiency or packing_efficiency,
            },
        )
    except EstimateError as e:
        raise click.BadParameter(str(e)) from None

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
    "List the regions skrooge has pricing for"
    try:
        instance_data = (
            find_instance_data(load_instance_types(), instance) if instance else None
        )
    except EstimateError as e:
        raise click.BadParameter(str(e)) from None
    matching_regions = available_regions(cost_class, instance_data)
    if not matching_regions:
        raise click.ClickException(
            f"No region has {cost_class or 'any'} pricing for {instance or 'any instance type'}."
        )
    click.echo("\n".join(matching_regions))


@cli.command(name="tui")
@click.argument(
    "workloads_file",
    type=click.Path(dir_okay=False, path_type=Path),
    default="skrooge.json",
)
def tui(workloads_file):
    """Interactively estimate one or more workloads, with live results

    Workloads are loaded from WORKLOADS_FILE if it exists, and saved to it
    with ctrl+s. Default: skrooge.json
    """
    # Imported here so the estimate command doesn't pay for loading Textual
    from rich.console import Console

    from .tui import SkroogeApp, load_workloads

    workloads, settings = [], None
    if workloads_file.exists():
        try:
            workloads, settings = load_workloads(workloads_file)
        except (OSError, TypeError, ValueError) as e:
            raise click.BadParameter(
                f"{workloads_file}: {e}", param_hint="WORKLOADS_FILE"
            ) from None

    app = SkroogeApp(workloads, workloads_file, settings=settings)
    app.run()
    # Leave the final numbers in the terminal once the TUI is gone
    if app.return_code == 0:
        Console().print(app.summary_table())


if __name__ == "__main__":
    cli()
