import json

import click


def render(format, data):
    if format == "english":
        render_english(data)
    elif format == "json":
        render_json(data)
    else:
        raise ValueError(f"Unknown format: {format}")


def render_english(data):
    click.echo(
        f"This workload is running on {data['instance']} instances in {data['region']} with {data['instance_specs']['cores']} cores and {data['instance_specs']['memory']}GiB of memory."
    )
    click.echo(
        f"This workload will require {data['delta_cpu'] / 1000} cores and {data['delta_mem'] / 1024} GiB of memory. This workload is {data['constrained_resource']}-constrained."
    )
    click.echo(
        f"This workload will require {data['required_instance_count']} instances, costing ${data['costs']['hourly']}/h (or ${data['costs']['monthly']}/m (or ${data['costs']['yearly']}/y)) at {data['costs']['class']} rates."
    )
    resource_costs = data["resource_costs"]
    if resource_costs:
        click.echo(
            f"Bin-packed in a cluster at {efficiency_text(data['packing_efficiency'])}, this workload will cost ${resource_costs['total']['hourly']}/h (or ${resource_costs['total']['monthly']}/m (or ${resource_costs['total']['yearly']}/y)): ${resource_costs['cores']['monthly']}/m for cores and ${resource_costs['memory']['monthly']}/m for memory."
        )
    else:
        click.echo(
            f"skrooge can't split {data['instance']} pricing into cores and memory, so there's no bin-packed estimate."
        )


def efficiency_text(packing_efficiency):
    cores, memory = packing_efficiency["cores"], packing_efficiency["memory"]
    if cores == memory:
        return f"{cores}% efficiency"
    return f"{cores}% CPU and {memory}% memory efficiency"


def render_json(data):
    click.echo(json.dumps(data))
