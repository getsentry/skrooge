import json

import click


def render(format, data):
    if format == "english":
        render_english(data)

    if format == "json":
        render_json(data)


def render_english(data):
    click.echo(
        f"This workload is running on {data['instance']} instances with {data['instance_specs']['cores']} cores and {data['instance_specs']['memory']}GiB of memory."
    )
    click.echo(
        f"This workload will require {data['delta_cpu'] / 1000} cores and {data['delta_mem'] / 1024} GiB of memory. This workload is {data['constrained_resource']}-constrained."
    )
    click.echo(
        f"This workload will require {data['required_instance_count']} instances, costing ${data['costs']['hourly']}/h (or ${data['costs']['monthly']}/m (or ${data['costs']['yearly']}/y))"
    )


def render_json(data):
    click.echo(json.dumps(data))
