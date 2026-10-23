import io
import json
import urllib.error
from pathlib import Path

import pytest

from skrooge import scraper
from skrooge.machine_types import MACHINE_TYPES, specs

FIXTURE = Path(__file__).parent / "fixtures" / "billing_catalog_skus.json"


@pytest.fixture
def pages():
    return json.loads(FIXTURE.read_text())["pages"]


@pytest.fixture
def skus(pages):
    return [sku for page in pages for sku in page["skus"]]


@pytest.fixture
def instances(skus):
    prices, _ = scraper.collect_prices(skus)
    return scraper.build_instances(prices)


def make_sku(description, usage_type="OnDemand", resource_group="CPU"):
    return {
        "skuId": "TEST",
        "description": description,
        "category": {
            "resourceFamily": "Compute",
            "resourceGroup": resource_group,
            "usageType": usage_type,
        },
    }


@pytest.mark.parametrize(
    "description,usage_type,resource_group,expected",
    [
        ("N2 Instance Core running in Americas", "OnDemand", "CPU", ("cores", "n2")),
        ("N2 Instance Ram running in Americas", "OnDemand", "RAM", ("memory", "n2")),
        (
            "Spot Preemptible N2D AMD Instance Core running in Paris",
            "Preemptible",
            "CPU",
            ("cores", "n2d"),
        ),
        (
            "Commitment v1: C2D AMD Ram in Americas for 3 Year",
            "Commit3Yr",
            "RAM",
            ("memory", "c2d"),
        ),
        (
            "N1 Predefined Instance Core running in Americas",
            "OnDemand",
            "N1Standard",
            ("cores", "n1"),
        ),
        (
            "Commitment v1: Cpu in Americas for 1 Year",
            "Commit1Yr",
            "CPU",
            ("cores", "n1"),
        ),
        (
            "T2A Arm Instance Core running in Americas",
            "OnDemand",
            "CPU",
            ("cores", "t2a"),
        ),
        (
            "Compute optimized Core running in Americas",
            "OnDemand",
            "CPU",
            ("cores", "c2"),
        ),
        (
            "Commitment v1: Memory-optimized Ram in Americas for 1 Year",
            "Commit1Yr",
            "RAM",
            ("memory", "m1"),
        ),
        (
            "M3 Memory-optimized Instance Core running in Americas",
            "OnDemand",
            "CPU",
            ("cores", "m3"),
        ),
        (
            "Nvidia Tesla A100 GPU running in Americas",
            "OnDemand",
            "GPU",
            ("gpu", "A100"),
        ),
        (
            "Nvidia A100 80GB GPU attached to Spot Preemptible VMs running in Americas",
            "Preemptible",
            "GPU",
            ("gpu", "A100 80GB"),
        ),
        (
            "Commitment v1: Nvidia L4 GPU in Americas for 1 Year",
            "Commit1Yr",
            "GPU",
            ("gpu", "L4"),
        ),
        (
            "Micro Instance with burstable CPU running in Americas",
            "OnDemand",
            "F1Micro",
            ("machine", "f1-micro"),
        ),
        (
            "Small Instance with 1 VCPU running in Americas",
            "OnDemand",
            "SomethingElse",
            ("machine", "g1-small"),
        ),
        # Priced differently from predefined machine types
        ("N2 Custom Instance Core running in Americas", "OnDemand", "CPU", None),
        ("N2 Sole Tenancy Instance Ram running in Americas", "OnDemand", "RAM", None),
        ("N2 Instance Extended Ram running in Americas", "OnDemand", "RAM", None),
        (
            "Nvidia Tesla T4 Virtual Workstation GPU running in Americas",
            "OnDemand",
            "GPU",
            None,
        ),
        # Only N1's commitments leave out the family
        ("Core running in Americas", "OnDemand", "CPU", None),
        ("Licensing Fee for Windows Server on N2 Core", "OnDemand", "CPU", None),
        (
            "Micro Instance with burstable CPU Sole Tenancy running in Americas",
            "OnDemand",
            "F1Micro",
            None,
        ),
    ],
)
def test_classify(description, usage_type, resource_group, expected):
    sku = make_sku(description, usage_type, resource_group)
    assert scraper.classify(sku) == expected


def test_classify_handles_missing_descriptions():
    assert scraper.classify(make_sku("")) is None


def test_classify_ignores_skus_outside_compute():
    sku = make_sku("N2 Instance Core running in Americas")
    sku["category"]["resourceFamily"] = "Storage"
    assert scraper.classify(sku) is None


def test_unit_price_adds_units_and_nanos():
    sku = {
        "skuId": "TEST",
        "pricingInfo": [
            {
                "pricingExpression": {
                    "usageUnit": "h",
                    "tieredRates": [
                        {
                            "startUsageAmount": 0,
                            "unitPrice": {
                                "currencyCode": "USD",
                                "units": "2",
                                "nanos": 500000000,
                            },
                        }
                    ],
                }
            }
        ],
    }
    assert scraper.unit_price(sku) == ("h", 2.5)


def test_unit_price_skips_a_free_tier(skus):
    g1_small = next(s for s in skus if s["description"].startswith("Small Instance"))
    assert scraper.unit_price(g1_small) == ("h", 0.025)


def test_unit_price_rejects_other_currencies(skus):
    sku = json.loads(json.dumps(skus[0]))
    sku["pricingInfo"][0]["pricingExpression"]["tieredRates"][0]["unitPrice"][
        "currencyCode"
    ] = "EUR"
    with pytest.raises(ValueError, match="isn't priced in USD"):
        scraper.unit_price(sku)


class FakeUrlopen:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def __call__(self, request, timeout):
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return io.BytesIO(json.dumps(response).encode())


def test_fetch_skus_follows_pages_and_sends_the_key_in_a_header(pages):
    urlopen = FakeUrlopen(pages)
    skus = list(scraper.fetch_skus("secret-key", urlopen=urlopen))

    assert len(skus) == sum(len(page["skus"]) for page in pages)
    assert len(urlopen.requests) == 2
    first, second = urlopen.requests
    assert first.full_url.startswith(scraper.SKUS_URL + "?")
    assert "currencyCode=USD" in first.full_url
    assert "pageToken" not in first.full_url
    assert "pageToken=page-2" in second.full_url
    for request in urlopen.requests:
        assert request.get_header("X-goog-api-key") == "secret-key"
        assert "secret-key" not in request.full_url


def http_error(code, message):
    body = io.BytesIO(
        json.dumps({"error": {"code": code, "message": message}}).encode()
    )
    return urllib.error.HTTPError(scraper.SKUS_URL, code, "Error", {}, body)


def test_fetch_skus_reports_api_errors_without_the_key():
    urlopen = FakeUrlopen([http_error(403, "API key not valid.")])
    with pytest.raises(RuntimeError) as excinfo:
        list(scraper.fetch_skus("secret-key", urlopen=urlopen))
    assert str(excinfo.value) == (
        "Cloud Billing API request failed with HTTP 403: API key not valid."
    )
    assert len(urlopen.requests) == 1


def test_fetch_skus_retries_server_errors(monkeypatch, pages):
    monkeypatch.setattr(scraper.time, "sleep", lambda seconds: None)
    urlopen = FakeUrlopen([http_error(503, "Unavailable"), *pages])
    assert len(list(scraper.fetch_skus("key", urlopen=urlopen))) > 0
    assert len(urlopen.requests) == 3


def test_collect_prices_indexes_by_kind_family_cost_class_and_region(skus):
    prices, stats = scraper.collect_prices(skus)

    assert prices["cores", "n2", "ondemand", "us-central1"] == pytest.approx(0.03)
    assert prices["memory", "n2", "ondemand", "us-east1"] == pytest.approx(0.004)
    assert prices["cores", "n2", "preemptible", "us-central1"] == pytest.approx(0.01)
    assert prices["memory", "n2", "cud-3y", "us-central1"] == pytest.approx(0.002)
    assert prices["cores", "n2", "ondemand", "europe-west1"] == pytest.approx(0.033)
    assert prices["cores", "n1", "cud-1y", "us-central1"] == pytest.approx(0.02)
    assert prices["gpu", "A100", "preemptible", "us-central1"] == pytest.approx(1.25)
    assert prices["machine", "f1-micro", "ondemand", "us-east1"] == pytest.approx(0.008)
    # Custom and sole-tenant SKUs are left out deliberately, so they aren't reported
    assert stats["unmatched"] == set()
    assert stats["conflicts"] == []


def test_collect_prices_reports_unrecognized_skus(skus):
    unknown = json.loads(json.dumps(skus[0]))
    unknown["description"] = "Z9 Brand New Instance Core running in Americas"
    _, stats = scraper.collect_prices([unknown])
    assert stats["unmatched"] == {"Z9 Brand New Instance Core (OnDemand)"}


def test_collect_prices_reports_conflicting_prices(skus):
    duplicate = json.loads(json.dumps(skus[0]))
    duplicate["pricingInfo"][0]["pricingExpression"]["tieredRates"][0]["unitPrice"][
        "nanos"
    ] = 40000000
    prices, stats = scraper.collect_prices([skus[0], duplicate])
    assert prices["cores", "n2", "ondemand", "us-central1"] == pytest.approx(0.03)
    assert len(stats["conflicts"]) == 2


def test_collect_prices_skips_unexpected_units(skus):
    sku = json.loads(json.dumps(skus[1]))
    sku["pricingInfo"][0]["pricingExpression"]["usageUnit"] = "GiBy.mo"
    prices, _ = scraper.collect_prices([sku])
    assert prices == {}


def test_build_instances_prices_machine_types_from_vcpu_and_memory(instances):
    # 2 vCPUs and 8 GiB
    assert instances["n2"]["n2-standard-2"]["regions"]["us-central1"] == {
        "ondemand": 0.092,
        "sud": 0.0736,
        "preemptible": 0.028,
        "cud-1y": 0.064,
        "cud-3y": 0.046,
    }
    assert instances["n2"]["n2-standard-2"]["regions"]["europe-west1"] == {
        "ondemand": 0.1012,
        "sud": 0.08096,
    }
    assert instances["n2"]["n2-standard-2"]["specs"] == specs("n2", "n2-standard-2")


def test_build_instances_n1(instances):
    # 1 vCPU and 3.75 GiB, with N1's commitment SKUs that have no family name
    assert instances["n1"]["n1-standard-1"]["regions"]["us-central1"] == {
        "ondemand": 0.045,
        "sud": 0.0315,
        "cud-1y": 0.03125,
    }


def test_build_instances_shared_core(instances):
    # f1 and g1 have their own SKUs, with no sustained use discount
    assert instances["f1"]["f1-micro"]["regions"]["us-east1"] == {
        "ondemand": 0.008,
        "preemptible": 0.004,
    }
    assert instances["g1"]["g1-small"]["regions"] == {
        "us-central1": {"ondemand": 0.025}
    }
    # e2-micro is billed for a quarter of a vCPU and 1 GiB, with no commitment prices
    assert instances["e2"]["e2-micro"]["regions"]["us-central1"] == {"ondemand": 0.008}
    assert instances["e2"]["e2-standard-2"]["regions"]["us-central1"] == {
        "ondemand": 0.064,
        "sud": 0.064,
    }
    assert instances["e2"]["e2-micro"]["specs"]["cores"] == 2


def test_build_instances_adds_gpus_without_sustained_use_discount(instances):
    # 12 vCPUs, 85 GiB and an A100. There's no preemptible A2 vCPU or memory price.
    assert instances["a2"]["a2-highgpu-1g"]["regions"] == {
        "us-central1": {"ondemand": 3.2, "sud": 3.2}
    }
    # Without an A100 80GB price, a2-ultragpu isn't priced at all
    assert instances["a2"]["a2-ultragpu-1g"]["regions"] == {}


def test_build_instances_sud_discounts_only_vcpus_and_memory(monkeypatch, skus):
    monkeypatch.setitem(scraper.SUD_MULTIPLIERS, "a2", 0.5)
    prices, _ = scraper.collect_prices(skus)
    output = scraper.build_instances(prices)
    assert output["a2"]["a2-highgpu-1g"]["regions"]["us-central1"]["sud"] == 2.85


def test_build_instances_keeps_every_family_and_machine_type(instances):
    assert list(instances) == [*MACHINE_TYPES, "resource_prices"]
    for family, machine_types in MACHINE_TYPES.items():
        assert list(instances[family]) == list(machine_types)


def test_build_resource_prices(instances):
    resource_prices = instances["resource_prices"]
    assert resource_prices["n2"]["us-central1"] == {
        "ondemand": {"cores": 0.03, "memory": 0.004},
        "sud": {"cores": 0.024, "memory": 0.0032},
        "preemptible": {"cores": 0.01, "memory": 0.001},
        "cud-1y": {"cores": 0.02, "memory": 0.003},
        "cud-3y": {"cores": 0.015, "memory": 0.002},
    }
    # GPUs aren't included
    assert resource_prices["a2"]["us-central1"]["ondemand"] == {
        "cores": 0.03,
        "memory": 0.004,
    }
    assert "f1" not in resource_prices
    assert "g1" not in resource_prices


def valid_instances():
    "Build output that passes validation, with every family priced in 20 regions"
    regions = [f"test-region{i}" for i in range(1, 20)] + ["us-central1"]
    prices = {}
    for family in MACHINE_TYPES:
        for region in regions:
            for kind in ["cores", "memory"]:
                prices[kind, family, "ondemand", region] = 0.01
            prices["machine", f"{family}-micro", "ondemand", region] = 0.01
            prices["machine", f"{family}-small", "ondemand", region] = 0.01
    for model in ["A100", "A100 80GB", "L4"]:
        for region in regions:
            prices["gpu", model, "ondemand", region] = 1.0
    return scraper.build_instances(prices)


def test_validate_accepts_complete_output():
    assert scraper.validate(valid_instances()) == []


def test_validate_rejects_empty_output():
    assert scraper.validate({}) == ["Output is empty"]


def test_validate_rejects_a_missing_family():
    data = valid_instances()
    del data["c3d"]
    errors = scraper.validate(data)
    assert errors[0] == "Missing top-level keys: c3d"
    assert errors[1:] == [f"{name} is missing" for name in MACHINE_TYPES["c3d"]]


def test_validate_rejects_a_family_without_prices():
    data = valid_instances()
    for instance in data["t2a"].values():
        instance["regions"] = {}
    assert "No t2a machine type has an on-demand price in us-central1" in (
        scraper.validate(data)
    )


def test_validate_rejects_bad_prices():
    data = valid_instances()
    regions = data["n2"]["n2-standard-2"]["regions"]
    regions["us-central1"]["preemptible"] = 0
    regions["test-region1"]["cud-1y"] = 99
    regions["test-region2"]["weekly"] = 1
    assert scraper.validate(data) == [
        "n2-standard-2 in test-region1 costs more cud-1y (99) than on demand (0.1)",
        "n2-standard-2 in test-region2 has an unknown cost class weekly",
        "n2-standard-2 in us-central1 has an invalid preemptible price 0",
    ]


def test_validate_rejects_changed_specs_and_too_few_regions():
    data = valid_instances()
    data["n2"]["n2-standard-2"]["specs"]["cores"] = 3
    errors = scraper.validate(data, min_regions=21)
    assert errors == [
        "n2-standard-2's specs don't match machine_types.py",
        "Only 20 regions have prices, expected at least 21",
    ]


def test_diff_reports_changes():
    old = {
        "n2": {
            "n2-standard-2": {
                "regions": {
                    "us": {"ondemand": 0.1},
                    "us-central1": {"ondemand": 0.1, "sud": 0.08},
                    "europe-west1": {"ondemand": 0.1},
                },
                "specs": {},
            },
            "n2-standard-4": {
                "regions": {"us-central1": {"ondemand": 0.2}},
                "specs": {},
            },
        },
        "license": {},
    }
    new = {
        "n2": {
            "n2-standard-2": {
                "regions": {
                    "us-central1": {"ondemand": 0.105, "sud": 0.084, "cud-1y": 0.06},
                    "europe-west1": {"ondemand": 0.15},
                    "us-south1": {"ondemand": 0.1},
                },
                "specs": {},
            },
        },
        "resource_prices": {},
    }
    report = scraper.diff(old, new)

    assert "- Added `resource_prices`" in report
    assert "- Removed `license`" in report
    assert "machine types removed: `n2-standard-4`" in report
    assert "regions added: `us-south1`" in report
    assert "regions removed: `us`" in report
    assert "`cud-1y` prices 0 → 1" in report
    assert "| n2 | 3 | 3 | +5.0% | +5.0% | +50.0% | ⚠️ 1 |" in report
    assert "### ⚠️ 1 prices changed by more than 20%" in report
    assert "| n2-standard-2 | europe-west1 | ondemand | 0.1 | 0.15 | +50.0% |" in report


def test_diff_without_changes():
    data = {"n2": {"n2-standard-2": {"regions": {"us-central1": {"ondemand": 0.1}}}}}
    report = scraper.diff(data, data)
    assert "No changes." in report
    assert "| n2 | 1 | 0 | +0.0% | +0.0% | +0.0% | 0 |" in report
    assert "⚠️" not in report


def test_main_scrape_requires_an_api_key(monkeypatch, capsys):
    monkeypatch.delenv(scraper.API_KEY_ENV, raising=False)
    assert scraper.main(["scrape"]) == 2
    assert "Set GCP_BILLING_API_KEY" in capsys.readouterr().err


def test_main_scrape_never_prints_the_api_key(monkeypatch, capsys):
    monkeypatch.setenv(scraper.API_KEY_ENV, "secret-key")

    def fail(api_key):
        raise RuntimeError("Cloud Billing API request failed with HTTP 400: Bad")
        yield

    monkeypatch.setattr(scraper, "fetch_skus", fail)
    assert scraper.main([]) == 1
    captured = capsys.readouterr()
    assert "HTTP 400" in captured.err
    assert "secret-key" not in captured.err + captured.out


def test_main_scrape_refuses_to_write_invalid_output(tmp_path, capsys):
    output = tmp_path / "instances.json"
    assert (
        scraper.main(["scrape", "--skus-file", str(FIXTURE), "--output", str(output)])
        == 1
    )
    assert not output.exists()
    assert "No c3d machine type has an on-demand price" in capsys.readouterr().err


def test_main_scrape_writes_valid_output(monkeypatch, tmp_path):
    monkeypatch.setattr(scraper, "validate", lambda data: [])
    output = tmp_path / "instances.json"
    dump = tmp_path / "skus.json"
    args = ["scrape", "--skus-file", str(FIXTURE), "--output", str(output)]
    assert scraper.main([*args, "--dump-skus", str(dump)]) == 0

    data = json.loads(output.read_text())
    assert data["n2"]["n2-standard-2"]["regions"]["us-central1"]["ondemand"] == 0.092
    assert len(scraper.load_skus(dump)) == 26


def test_main_validate_and_diff(tmp_path, capsys):
    path = tmp_path / "instances.json"
    path.write_text(json.dumps(valid_instances()))
    assert scraper.main(["validate", str(path)]) == 0

    path.write_text("{}")
    assert scraper.main(["validate", str(path)]) == 1
    assert "Output is empty" in capsys.readouterr().err

    assert scraper.main(["diff", str(path), str(path)]) == 0
    assert "## Price data changes" in capsys.readouterr().out
