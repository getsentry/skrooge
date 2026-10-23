import difflib
import functools
import json
import logging
import math
import re
from importlib.resources import files

logger = logging.getLogger(__name__)

COST_CLASSES = ["sud", "ondemand", "preemptible", "cud-1y", "cud-3y"]

MISSING_INSTANCE_TYPE_LINK = "https://github.com/getsentry/skrooge/issues/new?assignees=&labels=&projects=&template=BUG_REPORT.md"


class EstimateError(ValueError):
    "The inputs can't be estimated; the message explains why to the user"


class InstanceNotFoundError(EstimateError):
    pass


class PricingNotFoundError(EstimateError):
    pass


@functools.cache
def load_instance_types():
    return json.loads(
        files("skrooge").joinpath("instances.json").read_text(encoding="utf-8")
    )


def available_regions():
    # Skip aggregate pricing keys such as "us" or "asia-east"; GCP regions end in a digit
    return sorted(
        {
            region
            for family in load_instance_types().values()
            for instance_data in family.values()
            if instance_data
            for region in instance_data.get("regions", {})
            if region[-1].isdigit()
        },
        # Natural sort, so europe-west2 comes before europe-west10
        key=lambda region: [
            int(part) if part.isdigit() else part for part in re.split(r"(\d+)", region)
        ],
    )


def instance_names(instance_types):
    return [
        instance
        for family, instances in instance_types.items()
        if family != "license"
        for instance in instances
    ]


def find_instance_data(instance_types, instance):
    instance_family = instance.split("-")[0]
    try:
        return instance_types[instance_family][instance]
    except KeyError:
        pass

    if instance_family not in instance_types:
        logger.info(f"{instance_family}, {instance_types.keys()}")
        close_matches = difflib.get_close_matches(
            instance_family, instance_types.keys(), cutoff=0.4
        )
        raise InstanceNotFoundError(
            f"{instance_family} instance family not found. Did you mean: {', '.join(close_matches)}\nMissing an instance family that exists? {MISSING_INSTANCE_TYPE_LINK}"
        )

    close_matches = difflib.get_close_matches(
        instance, instance_types[instance_family].keys()
    )
    raise InstanceNotFoundError(
        f"{instance} not found. Did you mean: {', '.join(close_matches)}\nMissing an instance type that exists? {MISSING_INSTANCE_TYPE_LINK}"
    )


def check_pricing(instance_data, instance, cost_class, region):
    "Not every instance type has every cost class in every region"
    prices = instance_data["regions"].get(region, {})
    if cost_class in prices:
        return
    regions_with_pricing = [
        r
        for r, p in instance_data["regions"].items()
        if cost_class in p and r[-1].isdigit()
    ]
    suggestions = []
    if prices:
        suggestions.append(
            f"Cost classes available for {instance} in {region}: {', '.join(c for c in COST_CLASSES if c in prices)}"
        )
    close_matches = difflib.get_close_matches(region, regions_with_pricing)
    if close_matches:
        suggestions.append(
            f"Similar regions with {cost_class} pricing for {instance}: {', '.join(close_matches)}"
        )
    raise PricingNotFoundError(
        "\n".join(
            [f"No {cost_class} pricing for {instance} in {region}.", *suggestions]
        )
    )


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


def hourly_price(instance_data, cost_class, region):
    "The hourly price of one instance, or None if GCP doesn't offer it"
    return instance_data["regions"].get(region, {}).get(cost_class)


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


def calculate_estimate(
    instance_types, instance, replicas, cpu, mem, cost_class, region
):
    instance_data = find_instance_data(instance_types, instance)
    if not all(
        isinstance(instance_data["specs"][resource], (int, float))
        for resource in ("cores", "memory")
    ):
        raise EstimateError(
            f"{instance} is a shared-core instance type without a fixed number of cores, so skrooge can't estimate it."
        )
    check_pricing(instance_data, instance, cost_class, region)

    delta_cpu = replicas * abs(cpu)
    delta_mem = replicas * abs(mem)

    logger.info(f"{delta_cpu=}m {delta_mem=}MiB")

    constrained_resource = determine_constrained_resource(instance_data, cpu, mem)
    logger.info(f"{constrained_resource=}")

    if constrained_resource == "cores":
        resource_requirement = delta_cpu
    else:
        resource_requirement = delta_mem

    required_instance_count = determine_instance_count_required(
        instance_data, constrained_resource, resource_requirement
    )
    logger.info(f"{required_instance_count=}")

    costs = calculate_cost(
        instance_data,
        required_instance_count,
        cost_class=cost_class,
        region=region,
    )
    logger.info(costs)

    data = {
        "replicas": replicas,
        "cpu": cpu,
        "mem": mem,
        "delta_cpu": delta_cpu,
        "delta_mem": delta_mem,
        "constrained_resource": constrained_resource,
        "resource_requirement": resource_requirement,
        "required_instance_count": required_instance_count,
        "instance": instance,
        "instance_family": instance.split("-")[0],
        "instance_specs": instance_data["specs"],
        "costs": costs,
        "region": region,
    }

    logger.info(f"{data=}")
    return data
