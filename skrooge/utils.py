import difflib
import json
import logging
import math
from importlib.resources import files

logger = logging.getLogger(__name__)

COST_CLASSES = ["sud", "ondemand", "preemptible", "cud-1y", "cud-3y"]

REGIONS = [
    "asia-east1",
    "asia-east2",
    "asia-northeast1",
    "asia-northeast2",
    "asia-northeast3",
    "asia-south1",
    "asia-south2",
    "asia-southeast1",
    "asia-southeast2",
    "australia-southeast1",
    "australia-southeast2",
    "europe-central2",
    "europe-north1",
    "europe-southwest1",
    "europe-west1",
    "europe-west2",
    "europe-west3",
    "europe-west4",
    "europe-west6",
    "europe-west8",
    "europe-west9",
    "northamerica-northeast1",
    "northamerica-northeast2",
    "southamerica-east1",
    "southamerica-west1",
    "us-central1",
    "us-central2",
    "us-east1",
    "us-east4",
    "us-east5",
    "us-south1",
    "us-west1",
    "us-west2",
    "us-west3",
    "us-west4",
]

MISSING_INSTANCE_TYPE_LINK = "https://github.com/getsentry/skrooge/issues/new?assignees=&labels=&projects=&template=BUG_REPORT.md"


class InstanceNotFoundError(LookupError):
    pass


class PricingNotFoundError(LookupError):
    pass


def load_instance_types():
    return json.loads(
        files("skrooge").joinpath("instances.json").read_text(encoding="utf-8")
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


def determine_constrained_resource(instance_data, cpu, mem):
    logger.info(
        f"Calculating constrained resource: {instance_data['specs']=}, {cpu=}, {mem=}"
    )
    # A workload that only changes one resource is constrained by that resource
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
    if hourly_price(instance_data, cost_class, region) is None:
        raise PricingNotFoundError(
            f"No {cost_class} pricing for {instance} in {region}."
        )

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
