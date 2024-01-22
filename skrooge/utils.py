import math

import click

def determine_constrained_resource(instance_data, cpu, mem):
    click.echo(f"Calculating constrained resource: {instance_data=}, {cpu=}, {mem=}")
    if instance_data["cpu"] * 1000 / cpu > instance_data["memory"] * 1024 / mem:
        return "memory"
    else:
        return "cpu"

def determine_instance_count_required(instance_data, constrained_resource, resource_requirement):
    if constrained_resource == "cpu":
        normalization_factor = 1000
    else:
        normalization_factor = 1024

    resource_per_instance = instance_data[constrained_resource] * normalization_factor
    return math.ceil(resource_requirement / resource_per_instance)
