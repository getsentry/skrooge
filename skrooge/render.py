import json

import click

from .utils import SCALING_PATTERNS


def render(format, data):
    if format == "english":
        render_english(data)
    elif format == "json":
        render_json(data)
    else:
        raise ValueError(f"Unknown format: {format}")


def render_english(data):
    if data.get("autoscaling"):
        render_autoscaling_english(data)
        return
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


def render_autoscaling_english(data):
    autoscaling = data["autoscaling"]
    low, high = autoscaling["min"], autoscaling["max"]
    pattern = autoscaling["scaling_pattern"]
    click.echo(
        f"This workload is running on {data['instance']} instances in {data['region']} with {data['instance_specs']['cores']} cores and {data['instance_specs']['memory']}GiB of memory."
    )
    click.echo(
        f"Autoscaling between {low['replicas']} and {high['replicas']} replicas, this workload will require {low['delta_cpu'] / 1000} to {high['delta_cpu'] / 1000} cores and {low['delta_mem'] / 1024} to {high['delta_mem'] / 1024} GiB of memory. This workload is {data['constrained_resource']}-constrained."
    )
    click.echo(
        f"At {data['costs']['class']} rates, this workload will require {low['required_instance_count']} instances at {low['replicas']} replicas, costing {costs_text(low['costs'])}, and {high['required_instance_count']} instances at {high['replicas']} replicas, costing {costs_text(high['costs'])}."
    )
    click.echo(
        f"With the {pattern} scaling pattern ({SCALING_PATTERNS[pattern]['description']}), this workload will average {data['replicas']} replicas on {data['required_instance_count']} instances, costing {costs_text(data['costs'])} at {data['costs']['class']} rates."
    )
    resource_costs = data["resource_costs"]
    if resource_costs:
        click.echo(
            f"Bin-packed in a cluster at {efficiency_text(data['packing_efficiency'])}, this workload will cost ${low['resource_costs']['total']['monthly']}/m at {low['replicas']} replicas and ${high['resource_costs']['total']['monthly']}/m at {high['replicas']}, averaging {costs_text(resource_costs['total'])}: ${resource_costs['cores']['monthly']}/m for cores and ${resource_costs['memory']['monthly']}/m for memory."
        )
    else:
        click.echo(
            f"skrooge can't split {data['instance']} pricing into cores and memory, so there's no bin-packed estimate."
        )


def costs_text(costs):
    return f"${costs['hourly']}/h (or ${costs['monthly']}/m (or ${costs['yearly']}/y))"


def efficiency_text(packing_efficiency):
    cores, memory = packing_efficiency["cores"], packing_efficiency["memory"]
    if cores == memory:
        return f"{cores}% efficiency"
    return f"{cores}% CPU and {memory}% memory efficiency"


def render_json(data):
    click.echo(json.dumps(data))
