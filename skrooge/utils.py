import math

import click

def determine_constrained_resource(instance_data, cpu, mem):
    click.echo(f"Calculating constrained resource: {instance_data['specs']=}, {cpu=}, {mem=}")
    if instance_data["specs"]["cores"] * 1000 / cpu > instance_data["specs"]["memory"] * 1024 / mem:
        return "memory"
    else:
        return "cores"

def determine_instance_count_required(instance_data, constrained_resource, resource_requirement):
    if constrained_resource == "cores":
        normalization_factor = 1000
    else:
        normalization_factor = 1024

    resource_per_instance = instance_data["specs"][constrained_resource] * normalization_factor
    return math.ceil(resource_requirement / resource_per_instance)

def calculate_cost(instance_data, instance_count, region="us-central1", cost_type="ondemand"):
    hourly_cost = instance_data["regions"][region][cost_type] * instance_count
    costs = {
        "hourly": hourly_cost,
        "monthly": hourly_cost * 24 * 365 / 12,
        "yearly": hourly_cost * 24 * 365,
    }
    return costs
