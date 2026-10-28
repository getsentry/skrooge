import difflib
import functools
import json
import logging
import math
import re
import urllib.parse
from importlib.metadata import PackageNotFoundError, version
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

MISSING_INSTANCE_TYPE_TEMPLATE = "missing-instance-type.yml"

# How an autoscaling workload's load splits up a typical week, as (share of the
# time, load), where load 0 runs the minimum number of replicas and 1 the maximum
SCALING_PATTERNS = {
    "business-hours": {
        "description": "max replicas from 08:00 to 18:00 on weekdays, min the rest of the time",
        "levels": [(5 * 10 / (7 * 24), 1), (1 - 5 * 10 / (7 * 24), 0)],
    },
    "daytime": {
        "description": "max replicas from 08:00 to 18:00 every day, min overnight",
        "levels": [(10 / 24, 1), (14 / 24, 0)],
    },
    "diurnal": {
        "description": "a smooth daily curve from min replicas at night to max in the afternoon",
        "levels": [
            (1 / 24, (1 - math.cos(2 * math.pi * hour / 24)) / 2) for hour in range(24)
        ],
    },
    "hourly-spikes": {
        "description": "max replicas for 20 minutes of every hour, min the rest of the time",
        "levels": [(1 / 3, 1), (2 / 3, 0)],
    },
}

DEFAULT_SCALING_PATTERN = "business-hours"


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


def missing_instance_type_link(instance):
    "Link to a new issue asking for the instance type, with the issue form filled in"
    # The keys other than template and title are the form's field ids
    params = {
        "template": MISSING_INSTANCE_TYPE_TEMPLATE,
        "title": f"Add instance type: {instance}",
        "instance-type": instance,
    }
    try:
        params["version"] = version("skrooge")
    except PackageNotFoundError:
        pass
    return "https://github.com/getsentry/skrooge/issues/new?" + urllib.parse.urlencode(
        params
    )


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
            f"{instance_family} instance family not found. Did you mean: {', '.join(close_matches)}\nMissing an instance family that exists? {missing_instance_type_link(instance)}"
        )

    close_matches = difflib.get_close_matches(
        instance, instance_types[instance_family].keys()
    )
    raise InstanceNotFoundError(
        f"{instance} not found. Did you mean: {', '.join(close_matches)}\nMissing an instance type that exists? {missing_instance_type_link(instance)}"
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
    nodes have packing_efficiency["cores"] percent of their vCPUs and
    packing_efficiency["memory"] percent of their memory requested on average"""
    requested = {"cores": delta_cpu / 1000, "memory": delta_mem / 1024}
    costs = {
        resource: period_costs(
            amount * prices[resource] * (100 / packing_efficiency[resource])
        )
        for resource, amount in requested.items()
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
    packing_efficiency=None,
):
    """Estimate a change of cpu milli-cores and mem MiB in each of replicas

    packing_efficiency is the percentage of the cluster's vCPUs and memory that
    pods request, as {"cores": ..., "memory": ...}; 100 for both by default.
    """
    packing_efficiency = packing_efficiency or {"cores": 100, "memory": 100}
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


def replicas_at(load, min_replicas, max_replicas):
    "The replicas running at a load between 0 and 1, rounded up as the HPA does"
    # Round first so floating point error can't add a replica
    return min_replicas + math.ceil(round(load * (max_replicas - min_replicas), 6))


def is_percentage_pattern(scaling_pattern):
    return scaling_pattern.endswith("%")


def replicas_shares(scaling_pattern, min_replicas, max_replicas):
    """How much of the week a workload runs each number of replicas, as {replicas: share}

    scaling_pattern is a name in SCALING_PATTERNS, or a percentage like "25%" for a
    workload that runs max_replicas that share of the time and min_replicas the rest.
    """
    if is_percentage_pattern(scaling_pattern):
        at_max = float(scaling_pattern.removesuffix("%")) / 100
        levels = [(at_max, 1), (1 - at_max, 0)]
    else:
        levels = SCALING_PATTERNS[scaling_pattern]["levels"]
    shares = {}
    for share, load in levels:
        replicas = replicas_at(load, min_replicas, max_replicas)
        shares[replicas] = shares.get(replicas, 0) + share
    return shares


def calculate_autoscaling_estimate(
    instance_types,
    instance,
    min_replicas,
    max_replicas,
    cpu,
    mem,
    cost_class,
    region,
    scaling_pattern=DEFAULT_SCALING_PATTERN,
    packing_efficiency=None,
):
    """Estimate a change of cpu milli-cores and mem MiB in each replica of a workload
    that autoscales between min_replicas and max_replicas

    Returns calculate_estimate's result for the workload's average over the scaling
    pattern (see replicas_shares), so replicas and required_instance_count are
    averages. Its "autoscaling" key holds the pattern and the estimates at
    min_replicas and max_replicas.
    """
    shares = replicas_shares(scaling_pattern, min_replicas, max_replicas)
    estimates = {
        replicas: calculate_estimate(
            instance_types,
            instance,
            replicas,
            cpu,
            mem,
            cost_class=cost_class,
            region=region,
            packing_efficiency=packing_efficiency,
        )
        for replicas in {*shares, min_replicas, max_replicas}
    }
    # The cluster autoscaler adds and removes whole nodes as the replicas change
    average_replicas = sum(replicas * share for replicas, share in shares.items())
    average_instance_count = sum(
        estimates[replicas]["required_instance_count"] * share
        for replicas, share in shares.items()
    )
    logger.info(f"{average_replicas=} {average_instance_count=}")

    data = estimates[max_replicas]
    delta_cpu = average_replicas * abs(cpu)
    delta_mem = average_replicas * abs(mem)
    price = hourly_price(
        find_instance_data(instance_types, instance), cost_class, region
    )
    prices = data["resource_prices"]
    return {
        **data,
        "replicas": round(average_replicas, 2),
        "delta_cpu": round(delta_cpu),
        "delta_mem": round(delta_mem),
        "resource_requirement": round(
            delta_cpu if data["constrained_resource"] == "cores" else delta_mem
        ),
        "required_instance_count": round(average_instance_count, 2),
        "costs": {
            **period_costs(price * average_instance_count),
            "class": cost_class,
            "region": region,
        },
        "resource_costs": calculate_resource_cost(
            prices, delta_cpu, delta_mem, data["packing_efficiency"]
        )
        if prices
        else None,
        "autoscaling": {
            "scaling_pattern": scaling_pattern,
            "min_replicas": min_replicas,
            "max_replicas": max_replicas,
            **{
                bound: {
                    key: estimates[replicas][key]
                    for key in (
                        "replicas",
                        "delta_cpu",
                        "delta_mem",
                        "required_instance_count",
                        "costs",
                        "resource_costs",
                    )
                }
                for bound, replicas in (("min", min_replicas), ("max", max_replicas))
            },
        },
    }
