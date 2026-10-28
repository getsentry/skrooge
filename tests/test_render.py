import json
from functools import partial

import pytest

from skrooge.render import (
    SCROOGE,
    render,
    render_english,
    render_json,
    render_scrooge,
    scrooge_speech,
    speech_bubble,
)


@pytest.fixture
def estimate_data():
    return {
        "replicas": 3,
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
        "packing_efficiency": {"cores": 80, "memory": 80},
        "resource_costs": {
            "cores": {"hourly": 0.06, "monthly": 46, "yearly": 548},
            "memory": {"hourly": 0.01, "monthly": 4, "yearly": 44},
            "total": {"hourly": 0.07, "monthly": 50, "yearly": 592},
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
        (
            "Bin-packed in a cluster at 80% efficiency, this workload will cost "
            "$0.07/h (or $50/m (or $592/y)): $46/m for cores and $4/m for memory."
        ),
    ]


def test_render_english_with_packing_efficiency_by_resource(estimate_data, capsys):
    estimate_data["packing_efficiency"] = {"cores": 85, "memory": 55}

    render_english(estimate_data)

    last_line = capsys.readouterr().out.splitlines()[-1]
    assert last_line.startswith(
        "Bin-packed in a cluster at 85% CPU and 55% memory efficiency, this workload"
    )


def test_render_english_without_bin_packed_estimate(estimate_data, capsys):
    estimate_data["resource_costs"] = None

    render_english(estimate_data)

    assert capsys.readouterr().out.splitlines()[-1] == (
        "skrooge can't split n2-standard-2 pricing into cores and memory, "
        "so there's no bin-packed estimate."
    )


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


def test_scrooge_speech(estimate_data):
    assert scrooge_speech(estimate_data) == [
        "Hmph. A trifle, I grant thee, but a trifle is still a coin out of my purse.",
        (
            "Thy 3 replicas upon n2-standard-2 in us-central1 do want 2.5 cores and "
            "1.5 GiB of memory, and 'tis the cores that bindeth thee."
        ),
        (
            "2 whole nodes thou must have, at cud-1y rates: $0.25 the hour, $182 the "
            "month, and $2,190 the year!"
        ),
        (
            "Packed as tight as the coins in my strongbox, at 80% efficiency, "
            "'twould be $50 the month and $592 the year."
        ),
        (
            "And if thou art shrinking it, these be thy savings, and the first good "
            "news I have had all day."
        ),
        "Spend it, then, and begone! I have a counting-house to keep.",
    ]


@pytest.mark.parametrize(
    ("monthly", "opening"),
    [
        (999, "Hmph. A trifle"),
        (1000, "Bah! Humbug!"),
        (99999, "Bah! Humbug!"),
        (100000, "BAH! HUMBUG!"),
    ],
)
def test_scrooge_mood_depends_on_the_monthly_cost(estimate_data, monthly, opening):
    estimate_data["costs"]["monthly"] = monthly
    assert scrooge_speech(estimate_data)[0].startswith(opening)


def test_scrooge_speech_for_one(estimate_data):
    estimate_data.update(
        replicas=1, delta_cpu=1000, delta_mem=1024, required_instance_count=1
    )
    speech = scrooge_speech(estimate_data)
    assert speech[1].startswith(
        "Thy 1 replica upon n2-standard-2 in us-central1 doth want 1 core and 1 GiB"
    )
    assert speech[2].startswith("1 whole node thou must have")


@pytest.mark.parametrize("delta_cpu", [999, 1001])
def test_scrooge_speech_for_cores_that_round_to_one(estimate_data, delta_cpu):
    estimate_data["delta_cpu"] = delta_cpu
    assert " want 1 core and " in scrooge_speech(estimate_data)[1]


def test_scrooge_speech_without_bin_packed_estimate(estimate_data):
    estimate_data["resource_costs"] = None
    assert scrooge_speech(estimate_data)[3] == (
        "Nor will I split n2-standard-2's price into cores and memory, so thou "
        "gettest no cheaper reckoning from me."
    )


@pytest.mark.parametrize(
    "renderer",
    [render_scrooge, partial(render, "scrooge")],
    ids=["direct", "dispatch"],
)
def test_render_scrooge(estimate_data, renderer, capsys):
    renderer(estimate_data)

    captured = capsys.readouterr()
    assert captured.err == ""
    bubble = speech_bubble(scrooge_speech(estimate_data))
    assert captured.out == f"{bubble}\n{SCROOGE}\n"
    assert captured.out.isascii()
    assert max(len(line) for line in captured.out.splitlines()) <= 80


def test_speech_bubble():
    assert speech_bubble(["Bah! Humbug!", "Every penny!"]).splitlines() == [
        " ______________",
        "/ Bah! Humbug! \\",
        "|              |",
        "\\ Every penny! /",
        " --------------",
    ]


def test_speech_bubble_with_one_line():
    assert speech_bubble(["Humbug!"]).splitlines() == [
        " _________",
        "< Humbug! >",
        " ---------",
    ]


def test_speech_bubble_wraps():
    lines = speech_bubble(["word " * 30], width=20).splitlines()
    assert all(len(line) <= 24 for line in lines)
