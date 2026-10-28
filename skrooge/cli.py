import difflib
import logging
from pathlib import Path

import click
import click_log

from .render import render
from .utils import (
    COST_CLASSES,
    DEFAULT_SCALING_PATTERN,
    SCALING_PATTERNS,
    EstimateError,
    available_regions,
    calculate_autoscaling_estimate,
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


class ScalingPattern(click.Choice):
    "A choice of scaling pattern, or a percentage of max replicas like 60%"

    def convert(self, value, param, ctx):
        try:
            percentage = float(str(value).removesuffix("%"))
        except ValueError:
            return super().convert(value, param, ctx)
        if not 0 <= percentage <= 100:
            self.fail(f"{value!r} is not a percentage from 0 to 100.", param, ctx)
        return f"{percentage:g}%"

    def get_invalid_choice_message(self, value, ctx):
        return f"{super().get_invalid_choice_message(value, ctx).removesuffix('.')}, or a percentage like '60%'."


@click.group()
@click.version_option()
def cli():
    "A quick and dirty kubernetes cost estimator"


@cli.command(name="estimate")
@click_log.simple_verbosity_option(package_logger, default="ERROR")
@click.option(
    "-r",
    "--replicas",
    help="The number of replicas in the deployment. For an autoscaling one, use --min-replicas and --max-replicas instead",
    type=click.IntRange(min=1),
)
@click.option(
    "--min-replicas",
    help="The fewest replicas an autoscaling deployment is expected to run",
    type=click.IntRange(min=0),
)
@click.option(
    "--max-replicas",
    help="The most replicas an autoscaling deployment is expected to run",
    type=click.IntRange(min=1),
)
@click.option(
    "--scaling-pattern",
    help=f"How an autoscaling deployment's replicas vary over a week, for its average cost, or the percentage of --max-replicas it runs all the time, like 60%. Default: {DEFAULT_SCALING_PATTERN}",
    type=ScalingPattern(list(SCALING_PATTERNS), case_sensitive=False),
    metavar=f"[{'|'.join(SCALING_PATTERNS)}|N%]",
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
    type=click.Choice(["english", "json"], case_sensitive=False),
    default="english",
)
def estimate(
    replicas,
    min_replicas,
    max_replicas,
    scaling_pattern,
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
    logger.info(f"{replicas=} {min_replicas=} {max_replicas=} {scaling_pattern=}")
    logger.info(f"{cpu=}m")
    logger.info(f"{mem=}MiB")
    logger.info(f"{instance=}")

    autoscaling = min_replicas is not None or max_replicas is not None
    if replicas is not None and autoscaling:
        raise click.UsageError(
            "Pass either --replicas, or --min-replicas and --max-replicas, not both."
        )
    if autoscaling and (min_replicas is None or max_replicas is None):
        raise click.UsageError("Pass both --min-replicas and --max-replicas.")
    if replicas is None and not autoscaling:
        raise click.UsageError(
            "Missing option '-r' / '--replicas' (or --min-replicas and --max-replicas)."
        )
    if scaling_pattern and not autoscaling:
        raise click.UsageError(
            "--scaling-pattern needs --min-replicas and --max-replicas."
        )
    if autoscaling and min_replicas > max_replicas:
        raise click.BadParameter(
            f"{min_replicas} is more than --max-replicas {max_replicas}.",
            param_hint="'--min-replicas'",
        )

    if cpu == 0 and mem == 0:
        raise click.BadParameter("--cpu and --mem can't both be 0.")

    options = {
        "cost_class": cost_class,
        "region": region,
        "packing_efficiency": {
            "cores": cpu_packing_efficiency or packing_efficiency,
            "memory": mem_packing_efficiency or packing_efficiency,
        },
    }
    try:
        if autoscaling:
            data = calculate_autoscaling_estimate(
                load_instance_types(),
                instance,
                min_replicas,
                max_replicas,
                cpu,
                mem,
                scaling_pattern=scaling_pattern or DEFAULT_SCALING_PATTERN,
                **options,
            )
        else:
            data = calculate_estimate(
                load_instance_types(), instance, replicas, cpu, mem, **options
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
