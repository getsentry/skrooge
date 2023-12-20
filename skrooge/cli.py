import click


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

if __name__ == '__main__':
    cli()
