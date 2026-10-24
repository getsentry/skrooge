import asyncio
import functools
import json
from pathlib import Path

import pytest

from skrooge.tui import (
    Settings,
    SkroogeApp,
    Workload,
    estimate_workload,
    load_workloads,
    save_workloads,
)

# A fixed copy of part of instances.json (us-central1 only), so tests that check prices
# don't break when the bundled data is updated
instance_types = json.loads(
    (Path(__file__).parent / "fixtures" / "instances.json").read_text()
)


def workloads():
    return [
        Workload(
            name="web",
            replicas="30",
            cpu="2500",
            mem="2024",
            instance="n2-standard-32",
        ),
        Workload(
            name="worker",
            replicas="12",
            cpu="4000",
            mem="16384",
            instance="n2-highmem-16",
            cost_class="cud-1y",
        ),
        Workload(
            name="legacy-api",
            replicas="20",
            cpu="-2000",
            mem="-4096",
            instance="n1-standard-16",
        ),
    ]


def app_test(test):
    "Run an async test that drives the app with Textual's pilot"

    @functools.wraps(test)
    def wrapper(*args, **kwargs):
        asyncio.run(test(*args, **kwargs))

    return wrapper


def cell(app, row, column):
    table = app.query_one("#table")
    return str(table.get_cell(app.workloads[row].key, column))


def test_estimate_workload_matches_cli():
    data, error = estimate_workload(instance_types, workloads()[0])
    assert error is None
    assert data["required_instance_count"] == 3
    assert data["costs"]["hourly"] == 3.73
    assert data["costs"]["monthly"] == 2722
    assert data["costs"]["yearly"] == 32669


@pytest.mark.parametrize(
    ("changes", "error"),
    [
        ({"replicas": ""}, "Replicas must be a whole number"),
        ({"replicas": "-1"}, "Replicas must be a whole number"),
        ({"cpu": "-"}, "CPU change must be a whole number"),
        ({"mem": "1.5"}, "Memory change must be a whole number"),
        ({"instance": " "}, "Enter an instance type"),
        ({"instance": "n2-standard-33"}, "n2-standard-33 not found. Did you mean"),
        (
            {"instance": "m3-ultramem-32", "cost_class": "preemptible"},
            "No preemptible pricing for m3-ultramem-32 in us-central1",
        ),
    ],
)
def test_estimate_workload_reports_invalid_inputs(changes, error):
    workload = Workload(**changes)
    data, message = estimate_workload(instance_types, workload)
    assert data is None
    assert message.startswith(error)


def test_save_and_load_workloads(tmp_path):
    path = tmp_path / "skrooge.json"
    original = workloads()
    original[0].cpu = "-"  # partial input is kept as typed
    settings = Settings(
        cost_model="bin-packed",
        cpu_packing_efficiency="80",
        mem_packing_efficiency="60",
    )
    save_workloads(path, original, settings)

    saved = json.loads(path.read_text())
    assert saved["cost_model"] == "bin-packed"
    assert saved["cpu_packing_efficiency"] == 80
    assert saved["mem_packing_efficiency"] == 60
    assert saved["workloads"][0] == {
        "name": "web",
        "replicas": 30,
        "cpu": "-",
        "mem": 2024,
        "instance": "n2-standard-32",
        "region": "us-central1",
        "cost_class": "sud",
    }
    assert load_workloads(path) == (original, settings)


def test_load_workloads_defaults_settings(tmp_path):
    path = tmp_path / "skrooge.json"
    path.write_text('{"workloads": [{"name": "web"}]}')
    assert load_workloads(path) == ([Workload(name="web")], Settings())


@pytest.mark.parametrize(
    ("content", "error"),
    [
        ("not json", ValueError),
        ("[]", TypeError),
        ('{"workloads": {}}', TypeError),
        ('{"workloads": [1]}', TypeError),
        ('{"workloads": [{"memory": 1024}]}', ValueError),
        ('{"workloads": [{"region": "mars-north1"}]}', ValueError),
        ('{"workloads": [{"cost_class": "free"}]}', ValueError),
        ('{"workloads": [], "cost_model": "magic"}', ValueError),
        ('{"workloads": [], "efficiency": 80}', ValueError),
    ],
)
def test_load_workloads_rejects_invalid_files(tmp_path, content, error):
    path = tmp_path / "skrooge.json"
    path.write_text(content)
    with pytest.raises(error):
        load_workloads(path)


@app_test
async def test_mount_shows_estimates_without_changing_workloads(tmp_path):
    app = SkroogeApp(workloads(), tmp_path / "skrooge.json", instance_types)
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        assert app.workloads == workloads()
        assert not app.dirty
        assert app.query_one("#region").value == "us-central1"
        assert cell(app, 0, "nodes") == "3"
        assert cell(app, 0, "monthly") == "$2,722"
        # Scaling down is a saving
        assert cell(app, 2, "nodes") == "-3"
        assert cell(app, 2, "monthly") == "-$1,165"
        total = str(app.query_one("#total").render())
        assert "Net change: $4.11/h · $3,003/mo · $36,040/yr" in total


@app_test
async def test_editing_inputs_updates_estimate_live(tmp_path):
    app = SkroogeApp(workloads(), tmp_path / "skrooge.json", instance_types)
    async with app.run_test(size=(140, 40)) as pilot:
        app.query_one("#replicas").focus()
        await pilot.press("ctrl+u", "6", "0")
        await pilot.pause()
        assert app.workloads[0].replicas == "60"
        assert app.dirty
        # 60 * 2500m = 150 cores = 5 n2-standard-32 nodes
        assert cell(app, 0, "nodes") == "5"

        await pilot.press("ctrl+u")
        await pilot.pause()
        assert cell(app, 0, "nodes") == "⚠ invalid"
        assert "1 workload with invalid inputs not included" in str(
            app.query_one("#total").render()
        )


@app_test
async def test_selecting_rows_switches_workload(tmp_path):
    app = SkroogeApp(workloads(), tmp_path / "skrooge.json", instance_types)
    async with app.run_test(size=(140, 40)) as pilot:
        app.query_one("#table").focus()
        await pilot.press("down")
        await pilot.pause()
        assert app.selected == 1
        assert app.query_one("#name").value == "worker"
        assert app.query_one("#cost_class").value == "cud-1y"

        # Switching quickly must not leak one workload's values into another
        await pilot.press("down", "up", "down", "up", "up")
        await pilot.pause()
        assert app.selected == 0
        assert app.workloads == workloads()
        assert not app.dirty

        # Even when the form's Changed events arrive after the next switch
        app.select(1)
        app.select(2)
        await pilot.pause()
        assert app.workloads == workloads()
        assert not app.dirty


@app_test
async def test_add_and_remove_workloads(tmp_path):
    app = SkroogeApp(workloads(), tmp_path / "skrooge.json", instance_types)
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.press("ctrl+n")
        await pilot.pause()
        assert len(app.workloads) == 4
        assert app.selected == 3
        # A new workload is a copy of the selected one, ready to be renamed
        assert app.workloads[3].name == "workload-4"
        assert app.workloads[3].instance == "n2-standard-32"
        assert app.focused.id == "name"
        assert cell(app, 3, "nodes") == "3"

        await pilot.press("ctrl+r")
        await pilot.pause()
        assert [w.name for w in app.workloads] == ["web", "worker", "legacy-api"]
        assert app.selected == 2
        assert app.query_one("#name").value == "legacy-api"


@app_test
async def test_cannot_remove_the_only_workload(tmp_path):
    app = SkroogeApp([], tmp_path / "skrooge.json", instance_types)
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.press("ctrl+r")
        await pilot.pause()
        assert app.workloads == [Workload()]


@app_test
async def test_save_writes_workloads_file(tmp_path):
    path = tmp_path / "skrooge.json"
    app = SkroogeApp(workloads(), path, instance_types)
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.press("ctrl+n")
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert not app.dirty
    workloads_saved, _ = load_workloads(path)
    assert [w.name for w in workloads_saved] == [
        "web",
        "worker",
        "legacy-api",
        "workload-4",
    ]


@app_test
async def test_quit_warns_about_unsaved_changes(tmp_path):
    app = SkroogeApp(workloads(), tmp_path / "skrooge.json", instance_types)
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.press("ctrl+n")
        await pilot.press("ctrl+q")
        await pilot.pause()
        assert app.quit_warned
        assert app.return_code is None
        await pilot.press("ctrl+q")
    assert app.return_code == 0


def bin_packed(app_workloads, tmp_path):
    return SkroogeApp(
        app_workloads,
        tmp_path / "skrooge.json",
        instance_types,
        Settings(cost_model="bin-packed"),
    )


def total(app):
    return str(app.query_one("#total").render())


@app_test
async def test_toggling_cost_model_updates_table_and_total(tmp_path):
    app = SkroogeApp(workloads(), tmp_path / "skrooge.json", instance_types)
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.press("ctrl+b")
        await pilot.pause()
        assert app.settings.cost_model == "bin-packed"
        assert app.dirty
        # 75 cores and 59.3 GiB is $1,385 + $147 a month, 1.7 nodes' worth
        assert cell(app, 0, "nodes") == "1.7"
        assert cell(app, 0, "monthly") == "$1,532"
        assert "bin-packed at 100% across 3 workloads" in total(app)
        # The whole-node total is shown to compare
        assert "(with whole nodes: $3,003/mo)" in total(app)

        await pilot.press("ctrl+b")
        await pilot.pause()
        assert app.settings.cost_model == "whole-nodes"
        assert cell(app, 0, "monthly") == "$2,722"


@app_test
async def test_packing_efficiency_scales_bin_packed_costs(tmp_path):
    app = bin_packed(workloads(), tmp_path)
    async with app.run_test(size=(140, 40)) as pilot:
        app.query_one("#cpu_packing_efficiency").focus()
        await pilot.press("ctrl+u", "8", "0")
        app.query_one("#mem_packing_efficiency").focus()
        await pilot.press("ctrl+u", "8", "0")
        await pilot.pause()
        assert app.settings.cpu_packing_efficiency == "80"
        assert app.settings.mem_packing_efficiency == "80"
        # $1,385 / 0.8 + $147 / 0.8
        assert cell(app, 0, "monthly") == "$1,914"
        assert "bin-packed at 80% across" in total(app)

        # A cluster is usually short of one resource and has the other to spare
        await pilot.press("ctrl+u", "5", "0")
        await pilot.pause()
        # $1,385 / 0.8 + $147 / 0.5
        assert cell(app, 0, "monthly") == "$2,024"
        assert "bin-packed at 80% CPU, 50% memory across" in total(app)
        summary = str(app.query_one("#summary").render())
        assert "▶ Bin-packed at 80% CPU, 50% memory: " in summary

        await pilot.press("ctrl+u")
        await pilot.pause()
        assert cell(app, 0, "nodes") == "n/a"
        assert "Packing efficiencies must be whole numbers from 1 to 100" in total(app)
        # Whole-node estimates don't depend on them
        assert app.results[0][1] is None


@app_test
async def test_bin_packing_nets_each_resource_separately(tmp_path):
    # More CPU but less memory per replica, as when right-sizing requests
    rightsize = Workload(name="rightsize", replicas="50", cpu="500", mem="-1024")
    app = bin_packed([rightsize], tmp_path)
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        # 25 cores cost $462/mo and 50 GiB saves $124/mo
        assert cell(app, 0, "monthly") == "$338"
        await pilot.press("ctrl+b")
        await pilot.pause()
        # With whole nodes it's a whole extra node
        assert cell(app, 0, "monthly") == "$907"


@app_test
async def test_workloads_that_cant_be_bin_packed_are_left_out(tmp_path):
    c2 = Workload(
        name="c2", replicas="30", cpu="2500", mem="2024", instance="c2-standard-30"
    )
    app = bin_packed([*workloads(), c2], tmp_path)
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        assert cell(app, 3, "nodes") == "n/a"
        assert "across 3 workloads" in total(app)
        assert "1 workload can't be bin-packed, not included" in total(app)
        # The other model's total would cover different workloads
        assert "with whole nodes:" not in total(app)
