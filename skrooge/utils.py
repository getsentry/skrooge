import difflib
import functools
import json
import logging
import math
import re
from importlib.resources import files

from .machine_types import GPUS

logger = logging.getLogger(__name__)

COST_CLASSES = ["sud", "ondemand", "preemptible", "cud-1y", "cud-3y"]

PERIODS = ("hourly", "monthly", "yearly")

# Top-level keys in instances.json that aren't instance families
NON_FAMILY_KEYS = {"license", "resource_prices"}

# These have a fraction of a vCPU at a fraction of the price, whatever their specs say
SHARED_CORE_INSTANCE_TYPES = {
    "f1-micro",
    "g1-small",
    "e2-micro",
    "e2-small",
    "e2-medium",
}

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


def available_regions(cost_class=None, instance_data=None):
    "Regions with pricing, optionally only in one cost class or for one instance type"
    if instance_data is None:
        all_instance_data = [
            data
            for family in load_instance_types().values()
            for data in family.values()
            if data
        ]
    else:
        all_instance_data = [instance_data]
    # Skip aggregate pricing keys such as "us" or "asia-east"; GCP regions end in a digit
    return sorted(
        {
            region
            for data in all_instance_data
            for region, prices in data.get("regions", {}).items()
            if region[-1].isdigit() and (cost_class is None or cost_class in prices)
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
        if family not in NON_FAMILY_KEYS
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
    regions_with_pricing = available_regions(cost_class, instance_data)
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
    if regions_with_pricing:
        suggestions.append(
            f"List them all with: skrooge regions --instance {instance} --cost-class {cost_class}"
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


def period_costs(hourly_cost):
    return {
        "hourly": round(hourly_cost, 2),
        "monthly": round(hourly_cost * 24 * 365 / 12),
        "yearly": round(hourly_cost * 24 * 365),
    }


def calculate_cost(instance_data, instance_count, cost_class, region):
    hourly_cost = instance_data["regions"][region][cost_class] * instance_count
    return {**period_costs(hourly_cost), "class": cost_class, "region": region}


def derive_resource_prices(family_data, cost_class, region):
    """Solve for a family's price per vCPU and per GiB from its machine type prices

    GCP prices most machine types as vCPUs plus memory, so a least squares fit of
    price = cores * vCPU price + memory * GiB price recovers both, as long as the
    family has machine types with at least two memory-to-vCPU ratios.
    """
    shapes = [
        (data["specs"]["cores"], data["specs"]["memory"], price)
        for instance, data in family_data.items()
        if priced_by_resource(instance, data["specs"])
        and (price := hourly_price(data, cost_class, region))
    ]
    if len({memory / cores for cores, memory, _ in shapes}) < 2:
        return None
    cc = sum(cores * cores for cores, _, _ in shapes)
    cm = sum(cores * memory for cores, memory, _ in shapes)
    mm = sum(memory * memory for _, memory, _ in shapes)
    cp = sum(cores * price for cores, _, price in shapes)
    mp = sum(memory * price for _, memory, price in shapes)
    determinant = cc * mm - cm * cm
    prices = {
        "cores": (cp * mm - mp * cm) / determinant,
        "memory": (cc * mp - cm * cp) / determinant,
    }
    # Families priced some other way don't fit
    if not all(
        adds_up(prices, cores, memory, price) for cores, memory, price in shapes
    ):
        return None
    return prices


def priced_by_resource(instance, specs):
    """Whether an instance type's price could be just its vCPUs plus its memory

    Shared-core types have a fraction of their vCPUs at a fraction of the price,
    and GPU types' prices include their GPUs. A linear fit can absorb GPU prices
    when a family's GPUs scale with its vCPUs, so they're ruled out by name.
    """
    return (
        instance not in SHARED_CORE_INSTANCE_TYPES
        and instance not in GPUS
        and isinstance(specs["cores"], (int, float))
    )


def adds_up(prices, cores, memory, price):
    "Whether per-resource prices reproduce a machine type's price, to within 1%"
    return (
        abs(cores * prices["cores"] + memory * prices["memory"] - price) <= price / 100
    )


def resource_prices(instance_types, instance, cost_class, region):
    """The hourly price of one vCPU and one GiB of memory on an instance type

    Uses the prices recorded in instances.json, or derives them from the family's
    machine type prices. Returns None unless they add up to this instance type's
    price.
    """
    family = instance.split("-")[0]
    instance_data = instance_types[family][instance]
    specs = instance_data["specs"]
    price = hourly_price(instance_data, cost_class, region)
    if not price or not priced_by_resource(instance, specs):
        return None
    prices = (
        instance_types.get("resource_prices", {})
        .get(family, {})
        .get(region, {})
        .get(cost_class)
    ) or derive_resource_prices(instance_types[family], cost_class, region)
    if not prices or not adds_up(prices, specs["cores"], specs["memory"], price):
        return None
    return prices


def calculate_resource_cost(prices, delta_cpu, delta_mem, packing_efficiency):
    """The cost of just the CPU and memory a workload requests, in a cluster whose
    nodes have packing_efficiency percent of their resources requested on average"""
    overhead = 100 / packing_efficiency
    costs = {
        "cores": period_costs(delta_cpu / 1000 * prices["cores"] * overhead),
        "memory": period_costs(delta_mem / 1024 * prices["memory"] * overhead),
    }
    # Sum the rounded parts so the breakdown adds up to the total
    costs["total"] = {
        period: round(costs["cores"][period] + costs["memory"][period], 2)
        for period in PERIODS
    }
    return costs


def calculate_estimate(
    instance_types,
    instance,
    replicas,
    cpu,
    mem,
    cost_class,
    region,
    packing_efficiency=100,
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

    prices = resource_prices(instance_types, instance, cost_class, region)
    logger.info(f"{prices=}")

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
        "packing_efficiency": packing_efficiency,
        "resource_prices": prices,
        "resource_costs": calculate_resource_cost(
            prices, delta_cpu, delta_mem, packing_efficiency
        )
        if prices
        else None,
    }

    logger.info(f"{data=}")
    return data
