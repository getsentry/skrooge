import json
from functools import partial

import pytest

from skrooge.render import render, render_english, render_json


@pytest.fixture
def estimate_data():
    return {
        "instance": "n2-standard-2",
        "region": "us-central1",
        "instance_specs": {"cores": 2, "memory": 8},
        "delta_cpu": 2500,
        "delta_mem": 1536,
        "constrained_resource": "cores",
        "required_instance_count": 2,
        "costs": {
            "hourly": 0.25,
            "monthly": 182,
            "yearly": 2190,
            "class": "cud-1y",
            "region": "us-central1",
        },
    }


@pytest.mark.parametrize(
    "renderer",
    [render_english, partial(render, "english")],
    ids=["direct", "dispatch"],
)
def test_render_english(estimate_data, renderer, capsys):
    renderer(estimate_data)

    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out.splitlines() == [
        (
            "This workload is running on n2-standard-2 instances in us-central1 "
            "with 2 cores and 8GiB of memory."
        ),
        (
            "This workload will require 2.5 cores and 1.5 GiB of memory. "
            "This workload is cores-constrained."
        ),
        (
            "This workload will require 2 instances, costing $0.25/h "
            "(or $182/m (or $2190/y)) at cud-1y rates."
        ),
    ]


@pytest.mark.parametrize(
    "renderer",
    [render_json, partial(render, "json")],
    ids=["direct", "dispatch"],
)
def test_render_json(estimate_data, renderer, capsys):
    renderer(estimate_data)

    captured = capsys.readouterr()
    assert captured.err == ""
    assert json.loads(captured.out) == estimate_data
