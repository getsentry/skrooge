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
    load_instance_types,
)

logger = logging.getLogger(__name__)
# Configure the package logger so --verbosity also covers skrooge.utils
package_logger = logging.getLogger("skrooge")
click_log.basic_config(package_logger)


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
    help="The region to use for cost calculation. Default: us-central1",
    type=click.Choice(available_regions(), case_sensitive=False),
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
    "-f",
    "--format",
    help="The output format. Default: english",
    type=click.Choice(["english", "json"], case_sensitive=False),
    default="english",
)
def estimate(
    replicas, cpu, mem, instance, cost_class, region, packing_efficiency, format
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
            packing_efficiency=packing_efficiency,
        )
    except EstimateError as e:
        raise click.BadParameter(str(e)) from None

    render(format=format, data=data)


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
