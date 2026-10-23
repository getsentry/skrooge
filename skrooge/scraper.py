"""Generate instances.json from GCP's Cloud Billing Catalog API

    GCP_BILLING_API_KEY=... uv run python -m skrooge.scraper scrape --output new.json
    GCP_BILLING_ACCESS_TOKEN="$(gcloud auth print-access-token)" \
        uv run python -m skrooge.scraper scrape --output new.json
    uv run python -m skrooge.scraper validate new.json
    uv run python -m skrooge.scraper diff skrooge/instances.json new.json

Prices come from the Compute Engine service's SKUs. Most machine types are priced from
their family's per-vCPU and per-GiB SKUs, plus per-GPU SKUs for a2 and g2. f1-micro and
g1-small have per machine type SKUs. Specs are hard-coded in machine_types.py.
"""

import argparse
import json
import logging
import math
import os
import re
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from .machine_types import (
    E2_SHARED_CORE,
    GPUS,
    LEGACY_SHARED_CORE,
    MACHINE_TYPES,
    specs,
)

logger = logging.getLogger(__name__)

SERVICE_ID = "6F81-5844-456A"  # Compute Engine
SKUS_URL = f"https://cloudbilling.googleapis.com/v1/services/{SERVICE_ID}/skus"
API_KEY_ENV = "GCP_BILLING_API_KEY"
ACCESS_TOKEN_ENV = "GCP_BILLING_ACCESS_TOKEN"
QUOTA_PROJECT_ENV = "GCP_QUOTA_PROJECT"

COST_CLASSES = ["ondemand", "sud", "preemptible", "cud-1y", "cud-3y"]
USAGE_TYPES = {
    "OnDemand": "ondemand",
    "Preemptible": "preemptible",
    "Commit1Yr": "cud-1y",
    "Commit3Yr": "cud-3y",
}

# There's no SKU for sustained use discounts, so the sud price is the on-demand vCPU and
# memory price times this. GPUs don't get the discount.
SUD_MULTIPLIERS = {
    "n1": 0.7,
    "n2": 0.8,
    "n2d": 0.8,
    "e2": 1,
    "c2": 0.8,
    "c2d": 0.8,
    "c3": 1,
    "c3d": 1,
    "m1": 0.7,
    "m2": 0.7,
    "m3": 1,
    "a2": 1,
    "t2d": 1,
    "t2a": 0.7,
    "g2": 1,
    "c4d": 1,
    "n4d": 1,
    "n4a": 1,
}

# Families whose instance prices come from per-vCPU and per-GiB SKUs
RESOURCE_PRICED_FAMILIES = [f for f in MACHINE_TYPES if f not in LEGACY_SHARED_CORE]
# What the scraper uses, by kind. SKUs for anything else are ignored.
USED_KEYS = {
    "cores": {*RESOURCE_PRICED_FAMILIES, "m2-premium"},
    "memory": {*RESOURCE_PRICED_FAMILIES, "m2-premium"},
    "gpu": {model for model, _ in GPUS.values()},
    "machine": set(LEGACY_SHARED_CORE.values()),
}

# Prices are per hour, and memory prices per GiB-hour. Maps each kind of SKU to the
# base unit its price is converted from, and how many of those make up one of ours.
BASE_UNITS = {
    "cores": ("s", 3600),
    "memory": ("By.s", 2**30 * 3600),
    "gpu": ("s", 3600),
    "machine": ("s", 3600),
}
EXPECTED_UNITS = {"cores": "h", "memory": "GiBy.h", "gpu": "h", "machine": "h"}

# SKUs for these are priced differently from a family's predefined machine types
EXCLUDED_WORDS = {
    "calendar",
    "confidential",
    "custom",
    "dws",
    "extended",
    "flex",
    "flexible",
    "license",
    "licensing",
    "overcommit",
    "premium",
    "reserved",
    "sole",
    "tenancy",
    "upgrade",
    "workstation",
}
# Words in SKU descriptions that don't identify the family
FILLER_WORDS = {"amd", "arm", "instance", "intel", "predefined", "vm"}
FAMILY_QUALIFIERS = {"compute", "memory", "optimized", "memory-optimized"}
FAMILY_TOKEN = re.compile(r"^[a-z]\d+[a-z]?$")
REGION = re.compile(r"^[a-z]+(-[a-z]+)+\d+$")
DESCRIPTION = re.compile(
    r"^(?:Commitment(?: v\d+)?:\s*)?(?:Spot Preemptible |Preemptible )?"
    r"(?P<body>.+?)(?:\s+attached to .+?)?(?:\s+(?:running\s+)?in\s+.+)?$"
)
# M2 is priced as M1 plus these on-demand premiums, e.g. "Memory Optimized Upgrade Premium
# for Memory-optimized Instance Core running in Americas"
M2_PREMIUM = re.compile(
    r"^Memory Optimized Upgrade Premium for Memory-optimized Instance (Core|Ram)\b"
)
LEGACY_SHARED_CORE_SKUS = {
    "F1Micro": "f1-micro",
    "G1Small": "g1-small",
    "Micro Instance with burstable CPU": "f1-micro",
    "Small Instance with 1 VCPU": "g1-small",
}


def nice(number):
    return round(number, 5)


def natural_key(text):
    return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", text)]


def auth_headers(environ=os.environ):
    """Return headers that authenticate Cloud Billing API requests, or None

    Prefers an OAuth access token, e.g. from `gcloud auth print-access-token` or GitHub
    Actions workload identity federation, over an API key. Credentials go in headers so
    they can't end up in a logged URL.
    """
    token = environ.get(ACCESS_TOKEN_ENV)
    if token:
        headers = {"Authorization": f"Bearer {token}"}
        # User credentials may need a project to bill quota to
        if environ.get(QUOTA_PROJECT_ENV):
            headers["X-Goog-User-Project"] = environ[QUOTA_PROJECT_ENV]
        return headers
    api_key = environ.get(API_KEY_ENV)
    if api_key:
        return {"X-Goog-Api-Key": api_key}
    return None


def fetch_skus(headers, urlopen=urllib.request.urlopen, page_size=5000):
    "Yield every Compute Engine SKU, priced in USD"
    page_token = None
    while True:
        query = {"currencyCode": "USD", "pageSize": page_size}
        if page_token:
            query["pageToken"] = page_token
        request = urllib.request.Request(
            f"{SKUS_URL}?{urllib.parse.urlencode(query)}",
            headers={**headers, "Accept": "application/json"},
        )
        page = _get_json(request, urlopen)
        yield from page.get("skus", [])
        page_token = page.get("nextPageToken")
        if not page_token:
            return


def _get_json(request, urlopen, attempts=4):
    for attempt in range(attempts):
        try:
            with urlopen(request, timeout=60) as response:
                return json.load(response)
        except urllib.error.HTTPError as e:
            # Close the error's response body, which would otherwise leak
            with e:
                message = _api_error(e)
            retryable = e.code == 429 or e.code >= 500
            if not retryable or attempt == attempts - 1:
                raise RuntimeError(
                    f"Cloud Billing API request failed with HTTP {e.code}: {message}"
                ) from None
        except urllib.error.URLError as e:
            if attempt == attempts - 1:
                raise RuntimeError(
                    f"Cloud Billing API request failed: {e.reason}"
                ) from None
        time.sleep(2**attempt)


def _api_error(error):
    try:
        return json.load(error)["error"]["message"]
    except (ValueError, KeyError, TypeError):
        return error.reason


def unit_price(sku):
    """Return a SKU's usage unit and USD price per unit

    Uses the first non-zero tier, so a free tier doesn't make a SKU look free.
    """
    pricing = max(sku["pricingInfo"], key=lambda info: info.get("effectiveTime", ""))
    expression = pricing["pricingExpression"]
    rates = sorted(
        expression["tieredRates"], key=lambda rate: rate.get("startUsageAmount", 0)
    )
    price = 0
    for rate in rates:
        money = rate["unitPrice"]
        if money.get("currencyCode", "USD") != "USD":
            raise ValueError(f"{sku['skuId']} isn't priced in USD")
        price = int(money.get("units") or 0) + money.get("nanos", 0) / 1e9
        if price:
            break
    return expression["usageUnit"], price


def normalized_price(sku, kind):
    """Return a SKU's price per hour, or per GiB-hour for memory

    Converts using the SKU's own base unit, as some memory SKUs are priced per GB
    (GBy.h) rather than per GiB. Returns None if the SKU's units don't fit its kind.
    """
    unit, price = unit_price(sku)
    pricing = max(sku["pricingInfo"], key=lambda info: info.get("effectiveTime", ""))
    expression = pricing["pricingExpression"]
    base_unit, factor = BASE_UNITS[kind]
    if "baseUnitConversionFactor" not in expression:
        return price if unit == EXPECTED_UNITS[kind] else None
    if expression.get("baseUnit") != base_unit:
        return None
    return price * factor / float(expression["baseUnitConversionFactor"])


def description_body(sku):
    "Return a SKU's description without its usage type prefix or location"
    match = DESCRIPTION.match(sku.get("description", ""))
    return match["body"] if match else ""


def is_excluded(sku):
    """Whether a SKU prices something other than predefined machine types

    Checks the whole description, as GPU SKUs say how they're used after the GPU's
    name, e.g. "Nvidia L4 GPU attached to DWS Defined Duration VMs running in Iowa".
    """
    words = re.split(r"[\s()-]+", sku.get("description", "").lower())
    return bool(set(words) & EXCLUDED_WORDS)


def classify(sku):
    """Work out what a SKU prices from its category and description

    Returns (kind, key): ("cores", family), ("memory", family), ("gpu", model) or
    ("machine", machine type). Returns None for SKUs the scraper doesn't use.
    """
    category = sku.get("category", {})
    if category.get("resourceFamily") != "Compute":
        return None
    usage_type = category.get("usageType")
    premium = M2_PREMIUM.match(sku.get("description", ""))
    if premium:
        return ("cores" if premium[1] == "Core" else "memory"), "m2-premium"
    body = description_body(sku)
    if not body or is_excluded(sku):
        return None
    if category.get("resourceGroup") in LEGACY_SHARED_CORE_SKUS:
        return "machine", LEGACY_SHARED_CORE_SKUS[category["resourceGroup"]]
    if body in LEGACY_SHARED_CORE_SKUS:
        return "machine", LEGACY_SHARED_CORE_SKUS[body]

    words = body.lower().split()
    resource = words.pop()
    if resource == "gpu":
        model = " ".join(w for w in words if w not in {"nvidia", "tesla"})
        return ("gpu", model.upper()) if model else None
    if resource in {"core", "cpu", "vcpu"}:
        kind = "cores"
    elif resource in {"ram", "memory"}:
        kind = "memory"
    else:
        return None

    head = [w for w in words if w not in FILLER_WORDS]
    if not head:
        # N1's commitments are the only ones without a family name, e.g.
        # "Commitment v1: Cpu in Americas for 1 Year"
        return (kind, "n1") if usage_type in {"Commit1Yr", "Commit3Yr"} else None
    if FAMILY_TOKEN.match(head[0]) and set(head[1:]) <= FAMILY_QUALIFIERS:
        return kind, head[0]
    if head in (["compute", "optimized"], ["compute-optimized"]):
        return kind, "c2"
    if head in (["memory-optimized"], ["memory", "optimized"]):
        return kind, "m1"
    return None


def collect_prices(skus):
    """Index SKU prices by (kind, key, cost class, region)

    When SKUs disagree on a price, the one that covers fewer regions wins, so a
    region's own SKU beats a multi-region one. Returns the prices and stats on what was
    matched, to report on stderr.
    """
    found = {}
    stats = {"skus": 0, "matched": 0, "unmatched": set(), "conflicts": []}
    for sku in skus:
        stats["skus"] += 1
        category = sku.get("category", {})
        cost_class = USAGE_TYPES.get(category.get("usageType"))
        classified = classify(sku)
        if classified is None or cost_class is None:
            if _might_be_used(sku):
                stats["unmatched"].add(
                    f"{description_body(sku)} ({category.get('usageType')})"
                )
            continue
        kind, key = classified
        if key not in USED_KEYS[kind]:
            continue
        price = normalized_price(sku, kind)
        if price is None:
            logger.warning(
                "Skipping %s (%s): can't convert %s pricing to %s",
                sku.get("description"),
                sku.get("skuId"),
                unit_price(sku)[0],
                EXPECTED_UNITS[kind],
            )
            continue
        if not price:
            continue
        stats["matched"] += 1
        regions = [r for r in sku.get("serviceRegions", []) if REGION.match(r)]
        for region in regions:
            index = (kind, key, cost_class, region)
            candidate = (len(regions), price, sku)
            current = found.get(index)
            if current is None or candidate[0] < current[0]:
                found[index] = candidate
            elif candidate[0] == current[0] and not math.isclose(price, current[1]):
                stats["conflicts"].append((index, current[2], sku))
    # Drop conflicts that a more specific SKU settled
    stats["conflicts"] = [
        conflict
        for conflict in stats["conflicts"]
        if found[conflict[0]][2] is conflict[1]
    ]
    prices = {index: price for index, (_, price, _) in found.items()}
    add_m2_prices(prices)
    return prices, stats


def add_m2_prices(prices):
    """Price M2 vCPUs and memory as M1's plus the M2 upgrade premium

    The premium only has on-demand SKUs, so it's added in full to commitment prices too.
    M2 doesn't support Spot VMs, so it gets no preemptible price.
    """
    for (kind, key, cost_class, region), price in list(prices.items()):
        if key != "m1" or cost_class == "preemptible":
            continue
        premium = prices.get((kind, "m2-premium", "ondemand", region))
        if premium is not None:
            prices[kind, "m2", cost_class, region] = price + premium


def _might_be_used(sku):
    "Whether an unrecognized SKU mentions a family or GPU the scraper uses"
    category = sku.get("category", {})
    if category.get("resourceFamily") != "Compute":
        return False
    body = description_body(sku)
    if not body or is_excluded(sku):
        return False
    words = set(re.split(r"[\s(),:]+", body.lower()))
    return bool(
        words & USED_KEYS["cores"]
        or {w.lower() for model in USED_KEYS["gpu"] for w in model.split()} & words
        or "memory-optimized" in words
        or {"compute", "optimized"} <= words
    )


def machine_price(prices, family, machine_type, cost_class, region):
    """Return a machine type's hourly (vCPU and memory, GPU) prices

    Returns None if it isn't priced in that region and cost class.
    """
    if family in LEGACY_SHARED_CORE:
        price = prices.get(("machine", machine_type, cost_class, region))
        return None if price is None else (price, 0)

    if machine_type in E2_SHARED_CORE:
        if cost_class not in {"ondemand", "preemptible"}:
            return None
        cores, memory = E2_SHARED_CORE[machine_type]
    else:
        cores, memory = MACHINE_TYPES[family][machine_type][:2]

    core_price = prices.get(("cores", family, cost_class, region))
    memory_price = prices.get(("memory", family, cost_class, region))
    if core_price is None or memory_price is None:
        return None
    price = cores * core_price + memory * memory_price
    if machine_type in GPUS:
        model, count = GPUS[machine_type]
        gpu_price = prices.get(("gpu", model, cost_class, region))
        if gpu_price is None:
            return None
        return price, count * gpu_price
    return price, 0


def build_instances(prices):
    "Build instances.json's contents from collected prices"
    regions = sorted({index[3] for index in prices}, key=natural_key)
    output = {}
    for family, machine_types in MACHINE_TYPES.items():
        output[family] = {}
        for machine_type in machine_types:
            instance_regions = {}
            for region in regions:
                region_prices = {}
                for cost_class in COST_CLASSES:
                    if cost_class == "sud":
                        continue
                    price = machine_price(
                        prices, family, machine_type, cost_class, region
                    )
                    if price is None:
                        continue
                    resources, gpus = price
                    region_prices[cost_class] = nice(resources + gpus)
                    if (
                        cost_class == "ondemand"
                        and family in SUD_MULTIPLIERS
                        and machine_type not in E2_SHARED_CORE
                    ):
                        region_prices["sud"] = nice(
                            SUD_MULTIPLIERS[family] * resources + gpus
                        )
                if region_prices:
                    instance_regions[region] = {
                        c: region_prices[c] for c in COST_CLASSES if c in region_prices
                    }
            output[family][machine_type] = {
                "regions": instance_regions,
                "specs": specs(family, machine_type),
            }
    output["resource_prices"] = build_resource_prices(prices, regions)
    return output


def build_resource_prices(prices, regions):
    """Return each family's hourly price per vCPU and per GiB of memory

    For a2 and g2 these exclude GPUs, which their machine type prices include.
    """
    resource_prices = {}
    for family in RESOURCE_PRICED_FAMILIES:
        for region in regions:
            region_prices = {}
            for cost_class in COST_CLASSES:
                if cost_class == "sud":
                    continue
                core_price = prices.get(("cores", family, cost_class, region))
                memory_price = prices.get(("memory", family, cost_class, region))
                if core_price is None or memory_price is None:
                    continue
                region_prices[cost_class] = {
                    "cores": round(core_price, 8),
                    "memory": round(memory_price, 8),
                }
                if cost_class == "ondemand":
                    multiplier = SUD_MULTIPLIERS[family]
                    region_prices["sud"] = {
                        "cores": round(multiplier * core_price, 8),
                        "memory": round(multiplier * memory_price, 8),
                    }
            if region_prices:
                resource_prices.setdefault(family, {})[region] = {
                    c: region_prices[c] for c in COST_CLASSES if c in region_prices
                }
    return resource_prices


def validate(data, min_regions=20, check_region="us-central1"):
    "Return a list of problems that should stop instances.json from being updated"
    errors = []
    if not isinstance(data, dict) or not data:
        return ["Output is empty"]

    expected = [*MACHINE_TYPES, "resource_prices"]
    missing = [key for key in expected if key not in data]
    if missing:
        errors.append(f"Missing top-level keys: {', '.join(missing)}")
    unexpected = [key for key in data if key not in expected]
    if unexpected:
        errors.append(f"Unexpected top-level keys: {', '.join(unexpected)}")

    regions = set()
    for family, machine_types in MACHINE_TYPES.items():
        family_data = data.get(family, {})
        priced = 0
        for machine_type in machine_types:
            instance = family_data.get(machine_type)
            if instance is None:
                errors.append(f"{machine_type} is missing")
                continue
            if instance.get("specs") != specs(family, machine_type):
                errors.append(f"{machine_type}'s specs don't match machine_types.py")
            for region, region_prices in instance.get("regions", {}).items():
                regions.add(region)
                errors.extend(_check_prices(machine_type, region, region_prices))
            if "ondemand" in instance.get("regions", {}).get(check_region, {}):
                priced += 1
        if family in data and not priced:
            errors.append(
                f"No {family} machine type has an on-demand price in {check_region}"
            )

    for family in RESOURCE_PRICED_FAMILIES:
        if not data.get("resource_prices", {}).get(family):
            errors.append(f"resource_prices has no prices for {family}")

    if len(regions) < min_regions:
        errors.append(
            f"Only {len(regions)} regions have prices, expected at least {min_regions}"
        )
    return errors


def _check_prices(machine_type, region, region_prices):
    where = f"{machine_type} in {region}"
    for cost_class, price in region_prices.items():
        if cost_class not in COST_CLASSES:
            yield f"{where} has an unknown cost class {cost_class}"
        elif (
            not isinstance(price, (int, float))
            or not math.isfinite(price)
            or price <= 0
        ):
            yield f"{where} has an invalid {cost_class} price {price!r}"
    ondemand = region_prices.get("ondemand")
    if isinstance(ondemand, (int, float)):
        for cost_class in ["sud", "preemptible", "cud-1y", "cud-3y"]:
            price = region_prices.get(cost_class)
            if isinstance(price, (int, float)) and price > ondemand * 1.0001:
                yield f"{where} costs more {cost_class} ({price}) than on demand ({ondemand})"


def _instance_prices(data):
    "Flatten instances.json to {(family, machine type, region, cost class): price}"
    flat = {}
    for family, machine_types in data.items():
        if family in {"license", "resource_prices"} or not isinstance(
            machine_types, dict
        ):
            continue
        for machine_type, instance in machine_types.items():
            for region, region_prices in instance.get("regions", {}).items():
                for cost_class, price in region_prices.items():
                    flat[family, machine_type, region, cost_class] = price
    return flat


def diff(old, new, threshold=0.2, max_flagged=20):
    "Return a Markdown report of how new instances.json data differs from old"
    old_prices, new_prices = _instance_prices(old), _instance_prices(new)
    lines = ["## Price data changes", ""]

    added_keys = [k for k in new if k not in old]
    removed_keys = [k for k in old if k not in new]
    if added_keys or removed_keys:
        lines.append("### Top-level keys")
        lines += [f"- Added `{k}`" for k in added_keys]
        lines += [f"- Removed `{k}`" for k in removed_keys]
        lines.append("")

    families = [
        f
        for f in dict.fromkeys([*old, *new])
        if f not in {"license", "resource_prices"}
    ]
    lines.append("### Machine types, regions and cost classes")
    changes = False
    for family in families:
        old_types = set(old.get(family, {}))
        new_types = set(new.get(family, {}))
        notes = []
        if new_types - old_types:
            notes.append(f"machine types added: {_names(new_types - old_types)}")
        if old_types - new_types:
            notes.append(f"machine types removed: {_names(old_types - new_types)}")
        old_regions = {k[2] for k in old_prices if k[0] == family}
        new_regions = {k[2] for k in new_prices if k[0] == family}
        if new_regions - old_regions:
            notes.append(f"regions added: {_names(new_regions - old_regions)}")
        if old_regions - new_regions:
            notes.append(f"regions removed: {_names(old_regions - new_regions)}")
        for cost_class in COST_CLASSES:
            before = sum(1 for k in old_prices if k[0] == family and k[3] == cost_class)
            after = sum(1 for k in new_prices if k[0] == family and k[3] == cost_class)
            if before != after:
                notes.append(f"`{cost_class}` prices {before} → {after}")
        if notes:
            changes = True
            lines.append(f"- **{family}**: " + "; ".join(notes))
    if not changes:
        lines.append("No changes.")
    lines.append("")

    lines += [
        "### Price changes",
        "",
        "Compares prices present in both, by machine type, region and cost class.",
        "",
        (
            "| Family | Cost class | Compared | Changed | Median change | Min | Max "
            f"| Over ±{threshold:.0%} |"
        ),
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    changes = {}
    for key, old_price in old_prices.items():
        new_price = new_prices.get(key)
        if new_price is not None and old_price:
            changes[key] = (old_price, new_price, new_price / old_price - 1)
    flagged = {}
    for family in families:
        compared = False
        for cost_class in COST_CLASSES:
            ratios = [
                change
                for key, (_, _, change) in changes.items()
                if key[0] == family and key[3] == cost_class
            ]
            if not ratios:
                continue
            compared = True
            changed = sum(1 for r in ratios if abs(r) > 1e-9)
            over = sum(1 for r in ratios if abs(r) > threshold)
            lines.append(
                f"| {family} | {cost_class} | {len(ratios)} | {changed} "
                f"| {statistics.median(ratios):+.1%} | {min(ratios):+.1%} "
                f"| {max(ratios):+.1%} | {'⚠️ ' if over else ''}{over} |"
            )
        if not compared:
            lines.append(f"| {family} | | 0 | | | | | |")
    for key, (old_price, new_price, change) in changes.items():
        if abs(change) > threshold:
            flagged.setdefault(key[3], []).append((key, old_price, new_price, change))
    lines.append("")

    total = sum(len(items) for items in flagged.values())
    if total:
        lines += [
            f"### ⚠️ {total} prices changed by more than {threshold:.0%}",
            "",
            (
                f"Review these before merging. Shows up to {max_flagged} of the "
                "biggest changes for each cost class."
            ),
        ]
    for cost_class in COST_CLASSES:
        items = sorted(flagged.get(cost_class, []), key=lambda item: -abs(item[3]))
        if not items:
            continue
        lines += [
            "",
            f"#### `{cost_class}`: {len(items)}",
            "",
            "| Machine type | Region | Old | New | Change |",
            "| --- | --- | ---: | ---: | ---: |",
        ]
        for (_, machine_type, region, _), old_price, new_price, change in items[
            :max_flagged
        ]:
            lines.append(
                f"| {machine_type} | {region} | {old_price} | {new_price} "
                f"| {change:+.1%} |"
            )
        if len(items) > max_flagged:
            lines.append(f"\n…and {len(items) - max_flagged} more.")
    if total:
        lines.append("")
    return "\n".join(lines)


def _names(items, limit=15):
    items = sorted(items, key=natural_key)
    shown = ", ".join(f"`{item}`" for item in items[:limit])
    return shown + (f" and {len(items) - limit} more" if len(items) > limit else "")


def load_skus(path):
    "Load SKUs saved by --dump-skus, or a raw API response or list of them"
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        data = data.get("pages", [data])
    skus = []
    for item in data:
        skus.extend(item.get("skus", [item]) if "skus" in item else [item])
    return skus


def scrape(args):
    if args.skus_file:
        skus = load_skus(args.skus_file)
    else:
        headers = auth_headers()
        if headers is None:
            logger.error(
                "Set %s to an access token or %s to a Cloud Billing API key",
                ACCESS_TOKEN_ENV,
                API_KEY_ENV,
            )
            return 2
        try:
            skus = list(fetch_skus(headers))
        except RuntimeError as e:
            logger.error("%s", e)
            return 1
    if args.dump_skus:
        with open(args.dump_skus, "w", encoding="utf-8") as f:
            json.dump(skus, f)

    prices, stats = collect_prices(skus)
    logger.info("Read %d SKUs, used %d", stats["skus"], stats["matched"])
    for index, kept, ignored in stats["conflicts"]:
        logger.warning(
            "Conflicting %s prices for %s in %s: kept %s (%s, %s), ignored %s (%s, %s)",
            index[2],
            index[1],
            index[3],
            normalized_price(kept, index[0]),
            kept.get("description"),
            kept.get("skuId"),
            normalized_price(ignored, index[0]),
            ignored.get("description"),
            ignored.get("skuId"),
        )
    if stats["unmatched"]:
        logger.info(
            "Compute CPU, RAM and GPU SKUs that weren't recognized:\n  %s",
            "\n  ".join(sorted(stats["unmatched"])),
        )

    output = build_instances(prices)
    errors = validate(output)
    if errors:
        logger.error("Not writing invalid output:\n  %s", "\n  ".join(errors))
        return 1
    text = json.dumps(output) + "\n"
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(text)
    else:
        sys.stdout.write(text)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="python -m skrooge.scraper", description=__doc__.split("\n")[0]
    )
    commands = parser.add_subparsers(dest="command")
    scrape_parser = commands.add_parser(
        "scrape", help="Build instances.json from the Cloud Billing API"
    )
    scrape_parser.add_argument("--output", help="Write to this file instead of stdout")
    scrape_parser.add_argument(
        "--skus-file", help="Read SKUs from this file instead of the API"
    )
    scrape_parser.add_argument("--dump-skus", help="Save the SKUs read to this file")
    validate_parser = commands.add_parser(
        "validate", help="Check an instances.json file"
    )
    validate_parser.add_argument("path")
    diff_parser = commands.add_parser(
        "diff", help="Report changes between two instances.json files"
    )
    diff_parser.add_argument("old")
    diff_parser.add_argument("new")
    diff_parser.add_argument(
        "--threshold",
        type=float,
        default=0.2,
        help="Flag price changes bigger than this. Default: 0.2",
    )
    args = parser.parse_args(argv)
    if args.command is None:
        args = scrape_parser.parse_args([])
        args.command = "scrape"

    # Log to stderr for this run. cli.py configures the package logger for its own
    # output, so use this module's logger directly.
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    level, propagate = logger.level, logger.propagate
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    try:
        return run(args)
    finally:
        logger.removeHandler(handler)
        logger.setLevel(level)
        logger.propagate = propagate


def run(args):
    if args.command == "scrape":
        return scrape(args)
    if args.command == "validate":
        with open(args.path, encoding="utf-8") as f:
            errors = validate(json.load(f))
        for error in errors:
            logger.error("%s", error)
        return 1 if errors else 0
    with open(args.old, encoding="utf-8") as f:
        old = json.load(f)
    with open(args.new, encoding="utf-8") as f:
        new = json.load(f)
    sys.stdout.write(diff(old, new, threshold=args.threshold))
    return 0


if __name__ == "__main__":
    sys.exit(main())
