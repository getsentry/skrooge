import logging
import math

logger = logging.getLogger(__name__)


def determine_constrained_resource(instance_data, cpu, mem):
    logger.info(
        f"Calculating constrained resource: {instance_data['specs']=}, {cpu=}, {mem=}"
    )
    # A zero change in one resource means the other is the only constraint
    if cpu == 0:
        return "memory"
    if mem == 0:
        return "cores"
    if instance_data["specs"]["cores"] * 1000 / abs(cpu) > instance_data["specs"][
        "memory"
    ] * 1024 / abs(mem):
        return "memory"
    else:
        return "cores"


def determine_instance_count_required(
    instance_data, constrained_resource, resource_requirement
):
    if constrained_resource == "cores":
        normalization_factor = 1000
    else:
        normalization_factor = 1024

    resource_per_instance = (
        instance_data["specs"][constrained_resource] * normalization_factor
    )
    logger.info(f"{resource_per_instance=}, {resource_requirement=}")
    logger.info(f"{math.ceil(resource_requirement / resource_per_instance)=}")
    return math.ceil(resource_requirement / resource_per_instance)


def calculate_cost(instance_data, instance_count, cost_class, region):
    hourly_cost = instance_data["regions"][region][cost_class] * instance_count
    costs = {
        "hourly": round(hourly_cost, 2),
        "monthly": round(hourly_cost * 24 * 365 / 12),
        "yearly": round(hourly_cost * 24 * 365),
        "class": cost_class,
        "region": region,
    }
    return costs
