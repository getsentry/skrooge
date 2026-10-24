import json
from dataclasses import asdict, dataclass, fields, replace
from itertools import count

from rich.table import Table
from rich.text import Text
from textual.app import App
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.suggester import SuggestFromList
from textual.validation import Function, Integer
from textual.widgets import DataTable, Footer, Header, Input, Label, Select, Static

from .utils import (
    COST_CLASSES,
    PERIODS,
    EstimateError,
    InstanceNotFoundError,
    available_regions,
    calculate_cost,
    calculate_estimate,
    calculate_resource_cost,
    find_instance_data,
    hourly_price,
    instance_names,
    load_instance_types,
    resource_prices,
)

# A workload's replicas and per-replica CPU and memory, before and after its
# change, as Workload fields such as cpu_before, and the error when one is invalid
SIZES = {
    "replicas": ("Replicas", "a whole number"),
    "cpu": ("CPU", "a whole number of milli-cores"),
    "mem": ("Memory", "a whole number of MiB"),
}
NUMERIC_FIELDS = [f"{size}_{when}" for when in ("before", "after") for size in SIZES]

COST_MODELS = {"whole-nodes": "whole nodes", "bin-packed": "bin-packed"}

# The Settings field with each resource's packing efficiency
PACKING_EFFICIENCY_FIELDS = {
    "cores": "cpu_packing_efficiency",
    "memory": "mem_packing_efficiency",
}

COLUMNS = [
    ("name", "Workload"),
    ("replicas", "Replicas"),
    ("cpu", "CPU (m)"),
    ("mem", "Mem (MiB)"),
    ("instance", "Instance"),
    ("region", "Region"),
    ("cost_class", "Class"),
    ("nodes", "Nodes"),
    ("monthly", "$/month"),
    ("yearly", "$/year"),
]

_keys = count()


def from_dict(cls, data, what):
    "Build a Workload or Settings from a workloads file, keeping values as text"
    if not isinstance(data, dict):
        raise TypeError(f"each {what} must be an object")
    unknown = data.keys() - {f.name for f in fields(cls)}
    if unknown:
        raise ValueError(f"unknown {what} fields: {', '.join(sorted(unknown))}")
    return cls(**{name: str(value) for name, value in data.items()})


def to_dict(instance, numeric_fields):
    "The fields of a Workload or Settings, with valid numbers as numbers"
    data = asdict(instance)
    for name in numeric_fields:
        value = parse_int(data[name])
        if value is not None:
            data[name] = value
    return data


@dataclass
class Workload:
    # Numeric fields hold the text as typed so partial input survives switching
    # between workloads; estimate_workload() parses and validates them. A new
    # workload has no replicas before, and a removed one none after.
    name: str = "workload-1"
    replicas_before: str = "0"
    cpu_before: str = "1000"
    mem_before: str = "2048"
    replicas_after: str = "10"
    cpu_after: str = "1000"
    mem_after: str = "2048"
    instance: str = "n2-standard-32"
    region: str = "us-central1"
    cost_class: str = "sud"

    def __post_init__(self):
        self.key = f"workload-{next(_keys)}"

    @classmethod
    def from_dict(cls, data):
        workload = from_dict(cls, data, "workload")
        if workload.region not in available_regions():
            raise ValueError(f"unknown region: {workload.region}")
        if workload.cost_class not in COST_CLASSES:
            raise ValueError(f"unknown cost class: {workload.cost_class}")
        return workload

    def to_dict(self):
        return to_dict(self, NUMERIC_FIELDS)


@dataclass
class Settings:
    # Properties of the cluster, so shared by every workload
    cost_model: str = "whole-nodes"
    cpu_packing_efficiency: str = "100"
    mem_packing_efficiency: str = "100"

    @classmethod
    def from_dict(cls, data):
        settings = from_dict(cls, data, "settings")
        if settings.cost_model not in COST_MODELS:
            raise ValueError(f"unknown cost model: {settings.cost_model}")
        return settings

    def to_dict(self):
        return to_dict(self, PACKING_EFFICIENCY_FIELDS.values())

    def packing_efficiency(self):
        """The percentage of the cluster's vCPUs and memory that pods request, by
        resource, or None if either isn't valid"""
        efficiency = {
            resource: parse_int(getattr(self, field))
            for resource, field in PACKING_EFFICIENCY_FIELDS.items()
        }
        if all(
            value is not None and 1 <= value <= 100 for value in efficiency.values()
        ):
            return efficiency
        return None


def load_workloads(path):
    "Returns the workloads and settings in a workloads file"
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("workloads"), list):
        raise TypeError('expected an object with a "workloads" list')
    workloads = [Workload.from_dict(workload) for workload in data.pop("workloads")]
    return workloads, Settings.from_dict(data)


def save_workloads(path, workloads, settings):
    data = {
        **settings.to_dict(),
        "workloads": [workload.to_dict() for workload in workloads],
    }
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def parse_int(value):
    try:
        return int(value)
    except ValueError:
        return None


def workload_sizes(workload):
    "Returns (sizes, error), where sizes are the workload's numeric fields as numbers"
    sizes = {}
    for field in NUMERIC_FIELDS:
        value = parse_int(getattr(workload, field))
        if value is None or value < 0:
            size, when = field.split("_")
            label, kind = SIZES[size]
            return None, f"{label} {when} must be {kind}, 0 or more."
        sizes[field] = value
    return sizes, None


def requests(sizes, when):
    "The total CPU and memory a workload requests before or after its change"
    replicas = sizes[f"replicas_{when}"]
    return replicas * sizes[f"cpu_{when}"], replicas * sizes[f"mem_{when}"]


def estimate_workload(instance_types, workload, packing_efficiency=None):
    "Returns (data, error), exactly one of which is None"
    sizes, error = workload_sizes(workload)
    if error:
        return None, error
    instance = workload.instance.strip().lower()
    if not instance:
        return None, "Enter an instance type."
    cpu_before, mem_before = requests(sizes, "before")
    cpu_after, mem_after = requests(sizes, "after")
    try:
        # calculate_estimate() takes a change per replica, so give it the whole
        # change as one replica's
        data = calculate_estimate(
            instance_types,
            instance,
            1,
            cpu_after - cpu_before,
            mem_after - mem_before,
            cost_class=workload.cost_class,
            region=workload.region,
            packing_efficiency=packing_efficiency,
        )
    except EstimateError as e:
        return None, str(e)
    return data, None


def sign(change):
    return -1 if change < 0 else 1


def direction(data):
    "-1 if the workload shrinks the resource it's bound by (a saving), else 1"
    change = data["cpu"] if data["constrained_resource"] == "cores" else data["mem"]
    return sign(change)


def signed_resource_costs(data, resource_costs):
    """Bin-packed costs by period, where each resource is a cost or a saving
    on its own, so trading memory for CPU nets out"""
    signs = {"cores": sign(data["cpu"]), "memory": sign(data["mem"])}
    return {
        period: round(
            sum(
                signs[resource] * resource_costs[resource][period] for resource in signs
            ),
            2,
        )
        for period in PERIODS
    }


def model_costs(data, cost_model, packing_efficiency):
    """A workload's signed node count and costs by period under a cost model, or
    None if it can't be bin-packed. Bin-packed nodes are node-equivalents."""
    if cost_model == "whole-nodes":
        factor = direction(data)
        return {
            "nodes": factor * data["required_instance_count"],
            **{period: factor * data["costs"][period] for period in PERIODS},
        }
    if packing_efficiency is None or data["resource_costs"] is None:
        return None
    costs = signed_resource_costs(data, data["resource_costs"])
    prices, specs = data["resource_prices"], data["instance_specs"]
    node_price = specs["cores"] * prices["cores"] + specs["memory"] * prices["memory"]
    costs["nodes"] = costs["hourly"] / node_price
    return costs


def all_model_costs(data, packing_efficiency):
    if data is None:
        return None
    return {
        model: model_costs(data, model, packing_efficiency) for model in COST_MODELS
    }


def quantity(amount):
    return f"{amount:,.2f}".rstrip("0").rstrip(".")


def money(amount, decimals=0):
    prefix = "-" if amount < 0 else ""
    return f"{prefix}${abs(amount):,.{decimals}f}"


def nodes(count):
    return str(count) if isinstance(count, int) else f"{count:.1f}"


def model_label(cost_model, packing_efficiency):
    if cost_model == "whole-nodes":
        return "with whole nodes"
    if packing_efficiency is None:
        return "bin-packed"
    cores, memory = packing_efficiency["cores"], packing_efficiency["memory"]
    if cores == memory:
        return f"bin-packed at {cores}%"
    return f"bin-packed at {cores}% CPU, {memory}% memory"


def change_text(workload, size):
    "A size before and after the change as typed, or just once if it's the same"
    before = getattr(workload, f"{size}_before")
    after = getattr(workload, f"{size}_after")
    return after if before == after else f"{before} → {after}"


def signed(amount):
    return f"+{quantity(amount)}" if amount > 0 else quantity(amount)


def change_summary(data):
    "The workload's total change in CPU and memory"
    if data["cpu"] == 0 and data["mem"] == 0:
        return "No change in CPU or memory"
    bound = "CPU" if data["constrained_resource"] == "cores" else "memory"
    return (
        f"Total change: {signed(data['cpu'] / 1000)} cores, "
        f"{signed(data['mem'] / 1024)} GiB ({bound}-bound)"
    )


def row_cells(workload, error, costs):
    cells = [
        workload.name or "(unnamed)",
        *(change_text(workload, size) for size in SIZES),
        workload.instance,
        workload.region,
        workload.cost_class,
    ]
    if error:
        return [*cells, Text("⚠ invalid", style="bold red"), "", ""]
    if costs is None:
        return [*cells, Text("n/a", style="dim", justify="right"), "", ""]
    style = "green" if costs["hourly"] < 0 else ""
    return [
        *cells,
        Text(nodes(costs["nodes"]), style, justify="right"),
        Text(money(costs["monthly"]), style, justify="right"),
        Text(money(costs["yearly"]), style, justify="right"),
    ]


def total_text(costs, settings):
    "The net change across workloads, given each one's all_model_costs()"
    model, efficiency = settings.cost_model, settings.packing_efficiency()
    estimated = [workload for workload in costs if workload]
    included = [workload[model] for workload in estimated if workload[model]]
    hourly, monthly, yearly = (
        sum(workload[period] for workload in included) for period in PERIODS
    )
    text = Text.assemble(
        ("Net change: ", "bold"),
        (f"{money(hourly, 2)}/h · {money(monthly)}/mo · {money(yearly)}/yr", "bold"),
        f" {model_label(model, efficiency)}",
        f" across {len(included)} workload{'s' if len(included) != 1 else ''}",
    )
    # Show the other model's total to compare, if both cover every workload
    other = next(m for m in COST_MODELS if m != model)
    if estimated and all(all(workload.values()) for workload in estimated):
        other_monthly = sum(workload[other]["monthly"] for workload in estimated)
        text.append(
            f" ({model_label(other, efficiency)}: {money(other_monthly)}/mo)", "dim"
        )
    invalid = len(costs) - len(estimated)
    if invalid:
        text.append(
            f"  ⚠ {invalid} workload{'s' if invalid != 1 else ''} with invalid inputs not included",
            "bold red",
        )
    if model == "bin-packed" and efficiency is None:
        text.append(
            "  ⚠ Packing efficiencies must be whole numbers from 1 to 100", "bold red"
        )
    elif len(included) < len(estimated):
        unpackable = len(estimated) - len(included)
        text.append(
            f"  ⚠ {unpackable} workload{'s' if unpackable != 1 else ''} can't be bin-packed, not included",
            "bold red",
        )
    return text


def labelled(label, widget, classes="field"):
    return Horizontal(Label(label), widget, classes=classes)


class SkroogeApp(App):
    TITLE = "skrooge"
    SUB_TITLE = "Kubernetes scaling cost estimator"
    CSS = """
    #top {
        height: auto;
        max-height: 50%;
    }
    #inputs {
        width: 44;
        height: auto;
        border: round $primary;
        padding: 0 1;
    }
    #estimate {
        width: 1fr;
        height: auto;
        max-height: 100%;
        overflow-y: auto;
        border: round $primary;
        padding: 0 1;
    }
    .field {
        height: 1;
    }
    .field Label {
        width: 15;
        color: $text-muted;
    }
    .field Input, .field Select {
        width: 1fr;
    }
    .field .column {
        width: 1fr;
    }
    .field .arrow {
        width: 3;
    }
    .hint {
        margin-top: 1;
        color: $text-muted;
    }
    #tiers {
        height: auto;
        margin-top: 1;
    }
    #settings {
        height: 1;
        padding: 0 2;
    }
    .setting {
        width: auto;
        margin-right: 4;
    }
    .setting Label {
        margin-right: 1;
        color: $text-muted;
    }
    #cost_model {
        width: 17;
    }
    #cpu_packing_efficiency, #mem_packing_efficiency {
        width: 6;
    }
    #table {
        height: 1fr;
        min-height: 5;
        border: round $primary;
    }
    #total {
        padding: 0 1;
    }
    """
    BINDINGS = (
        Binding("ctrl+n", "add_workload", "Add workload", priority=True),
        Binding("ctrl+r", "remove_workload", "Remove workload", priority=True),
        Binding("ctrl+b", "toggle_cost_model", "Cost model", priority=True),
        Binding("ctrl+s", "save", "Save", priority=True),
    )

    def __init__(self, workloads, path, instance_types=None, settings=None):
        super().__init__()
        self.instance_types = instance_types or load_instance_types()
        self.workloads = list(workloads) or [Workload()]
        self.settings = settings or Settings()
        self.path = path
        self.selected = 0
        self.results = []
        self.costs = []
        self.dirty = False
        self.quit_warned = False

    def compose(self):
        names = instance_names(self.instance_types)
        known = set(names)
        # Start the form on the first workload, so the widgets' initial Changed
        # events agree with the model
        first = self.workloads[0]
        yield Header()
        with Horizontal(id="top"):
            with Vertical(id="inputs"):
                yield labelled("Name", Input(first.name, id="name", compact=True))
                yield Horizontal(
                    Label(""),
                    Label("Before", classes="column"),
                    Label("", classes="arrow"),
                    Label("After", classes="column"),
                    classes="field",
                )
                for size, label in (
                    ("replicas", "Replicas"),
                    ("cpu", "CPU (m)"),
                    ("mem", "Memory (MiB)"),
                ):
                    before, after = (
                        Input(
                            getattr(first, f"{size}_{when}"),
                            id=f"{size}_{when}",
                            type="integer",
                            validators=[Integer(minimum=0)],
                            compact=True,
                        )
                        for when in ("before", "after")
                    )
                    yield Horizontal(
                        Label(label),
                        before,
                        Label(" → ", classes="arrow"),
                        after,
                        classes="field",
                    )
                yield labelled(
                    "Instance type",
                    Input(
                        first.instance,
                        id="instance",
                        suggester=SuggestFromList(names, case_sensitive=False),
                        validators=[
                            Function(
                                lambda value: value.strip().lower() in known,
                                "Unknown instance type",
                            )
                        ],
                        compact=True,
                    ),
                )
                yield labelled(
                    "Region",
                    Select(
                        [(region, region) for region in available_regions()],
                        value=first.region,
                        id="region",
                        allow_blank=False,
                        compact=True,
                    ),
                )
                yield labelled(
                    "Cost class",
                    Select(
                        [(cost_class, cost_class) for cost_class in COST_CLASSES],
                        value=first.cost_class,
                        id="cost_class",
                        allow_blank=False,
                        compact=True,
                    ),
                )
                yield Static("CPU and memory are per replica.", classes="hint")
            with Vertical(id="estimate"):
                yield Static(id="summary")
                yield DataTable(id="tiers", cursor_type="none")
        with Horizontal(id="settings"):
            yield labelled(
                "Cost model",
                Select(
                    [(label, model) for model, label in COST_MODELS.items()],
                    value=self.settings.cost_model,
                    id="cost_model",
                    allow_blank=False,
                    compact=True,
                ),
                classes="setting",
            )
            with Horizontal(classes="setting"):
                yield Label("Packing efficiency (%)")
                for resource, field in PACKING_EFFICIENCY_FIELDS.items():
                    yield Label("CPU" if resource == "cores" else "memory")
                    yield Input(
                        getattr(self.settings, field),
                        id=field,
                        type="integer",
                        validators=[Integer(minimum=1, maximum=100)],
                        compact=True,
                    )
        yield DataTable(id="table", cursor_type="row", zebra_stripes=True)
        yield Static(id="total")
        yield Footer()

    def on_mount(self):
        self.query_one("#inputs").border_title = "Inputs"
        tiers = self.query_one("#tiers", DataTable)
        tiers.can_focus = False
        tiers.add_column("Cost class")
        for label in ("$/node/h", "$/vCPU/h", "$/GiB/h", "Nodes $/mo", "Packed $/mo"):
            tiers.add_column(Text(label, justify="right"))
        table = self.query_one("#table", DataTable)
        for key, label in COLUMNS:
            table.add_column(label, key=key)
        self.refresh_estimates()
        self.select(0)

    def refresh_estimates(self):
        efficiency = self.settings.packing_efficiency()
        self.results = [
            estimate_workload(self.instance_types, workload, efficiency)
            for workload in self.workloads
        ]
        self.costs = [all_model_costs(data, efficiency) for data, _ in self.results]
        table = self.query_one("#table", DataTable)
        table.border_title = (
            f"Workloads · {model_label(self.settings.cost_model, efficiency)}"
        )
        for workload, (_, error), costs in zip(
            self.workloads, self.results, self.costs, strict=True
        ):
            cells = row_cells(
                workload, error, costs and costs[self.settings.cost_model]
            )
            if workload.key in table.rows:
                for (column, _), cell in zip(COLUMNS, cells, strict=True):
                    table.update_cell(workload.key, column, cell, update_width=True)
            else:
                table.add_row(*cells, key=workload.key)
        self.query_one("#total", Static).update(total_text(self.costs, self.settings))
        self.show_estimate()

    def show_estimate(self):
        workload = self.workloads[self.selected]
        data, error = self.results[self.selected]
        costs = self.costs[self.selected]
        efficiency = self.settings.packing_efficiency()
        self.query_one(
            "#estimate"
        ).border_title = f"Estimate · {workload.name or '(unnamed)'}"
        instance = workload.instance.strip().lower()
        try:
            instance_data = find_instance_data(self.instance_types, instance)
        except InstanceNotFoundError:
            instance_data = None

        if error:
            summary = Text(error, "red")
        else:
            specs = data["instance_specs"]
            summary = Text.assemble(
                (data["instance"], "bold"),
                f": {specs['cores']} cores, {specs['memory']} GiB per node\n",
                change_summary(data),
            )
            for model in COST_MODELS:
                summary.append("\n")
                summary.append_text(self.model_summary(data, costs, model, efficiency))
        self.query_one("#summary", Static).update(summary)

        tiers = self.query_one("#tiers", DataTable)
        tiers.clear()
        for cost_class in COST_CLASSES:
            current = cost_class == workload.cost_class
            label = Text(
                f"{'▶' if current else ' '} {cost_class}", "bold" if current else ""
            )
            price = instance_data and hourly_price(
                instance_data, cost_class, workload.region
            )
            prices = price and resource_prices(
                self.instance_types, instance, cost_class, workload.region
            )
            if not price:
                cells = ["n/a", "", "", "", ""]
            else:
                cells = [money(price, 2)]
                cells += (
                    [money(prices["cores"], 4), money(prices["memory"], 4)]
                    if prices
                    else ["n/a", "n/a"]
                )
                if data is None:
                    cells += ["—", "—"]
                else:
                    count = data["required_instance_count"]
                    whole = calculate_cost(
                        instance_data, count, cost_class, workload.region
                    )
                    cells.append(money(direction(data) * whole["monthly"]))
                    if prices and efficiency:
                        packed = calculate_resource_cost(
                            prices, data["delta_cpu"], data["delta_mem"], efficiency
                        )
                        cells.append(
                            money(signed_resource_costs(data, packed)["monthly"])
                        )
                    else:
                        cells.append("n/a")
            tiers.add_row(
                label,
                *(
                    Text(cell, "bold" if current else "", justify="right")
                    for cell in cells
                ),
            )

    def model_summary(self, data, costs, model, efficiency):
        "One line on the selected workload's cost under a cost model"
        active = model == self.settings.cost_model
        label = model_label(model, efficiency)
        text = Text(f"{'▶' if active else ' '} {label[0].upper()}{label[1:]}: ")
        model_costs = costs[model]
        if model_costs is None:
            text.append(
                "enter packing efficiencies from 1 to 100"
                if efficiency is None
                else f"skrooge can't split {data['instance']} pricing into cores and memory",
                "dim",
            )
            return text
        style = ("bold " if active else "") + (
            "green" if model_costs["hourly"] < 0 else ""
        )
        count = model_costs["nodes"]
        worth = "" if model == "whole-nodes" else "' worth"
        text.append(
            f"{nodes(count)} node{'s' if count != 1 else ''}{worth} · "
            f"{money(model_costs['hourly'], 2)}/h · {money(model_costs['monthly'])}/mo · "
            f"{money(model_costs['yearly'])}/yr",
            style,
        )
        if model == "bin-packed":
            parts = data["resource_costs"]
            text.append(
                f"\n    cores {money(sign(data['cpu']) * parts['cores']['monthly'])}/mo"
                f" · memory {money(sign(data['mem']) * parts['memory']['monthly'])}/mo",
                "dim",
            )
        return text

    def select(self, index):
        self.selected = index
        workload = self.workloads[index]
        for name in ("name", *NUMERIC_FIELDS, "instance"):
            self.query_one(f"#{name}", Input).value = getattr(workload, name)
        self.query_one("#region", Select).value = workload.region
        self.query_one("#cost_class", Select).value = workload.cost_class
        self.show_estimate()
        self.query_one("#table", DataTable).move_cursor(row=index)

    def mark_dirty(self):
        self.dirty = True
        self.quit_warned = False

    def field_changed(self, widget):
        # Only the form and settings; the command palette's input bubbles up too
        if widget.parent.has_class("field"):
            target = self.workloads[self.selected]
        elif widget.parent.has_class("setting"):
            target = self.settings
        else:
            return
        # Filling in the form in select() also posts Changed events, which may
        # arrive after the selection has moved on. Reading the widget's current
        # value rather than the event's makes those no-ops.
        if getattr(target, widget.id) == widget.value:
            return
        setattr(target, widget.id, widget.value)
        self.mark_dirty()
        self.refresh_estimates()

    def on_input_changed(self, event):
        self.field_changed(event.input)

    def on_select_changed(self, event):
        self.field_changed(event.select)

    def on_data_table_row_highlighted(self, event):
        if event.data_table.id != "table":
            return
        # Like the form's events, these can be stale (and select() posts more
        # of them), so follow where the cursor is now
        index = event.data_table.cursor_row
        if index != self.selected and 0 <= index < len(self.workloads):
            self.select(index)

    def action_toggle_cost_model(self):
        select = self.query_one("#cost_model", Select)
        select.value = next(model for model in COST_MODELS if model != select.value)

    def action_add_workload(self):
        names = {workload.name for workload in self.workloads}
        number = len(self.workloads) + 1
        while f"workload-{number}" in names:
            number += 1
        # Start from a copy of the selected workload: most share an instance type
        self.workloads.append(
            replace(self.workloads[self.selected], name=f"workload-{number}")
        )
        self.mark_dirty()
        self.refresh_estimates()
        self.select(len(self.workloads) - 1)
        self.query_one("#name", Input).focus()

    def action_remove_workload(self):
        if len(self.workloads) == 1:
            self.notify("Can't remove the only workload.", severity="warning")
            return
        removed = self.workloads.pop(self.selected)
        self.query_one("#table", DataTable).remove_row(removed.key)
        self.selected = min(self.selected, len(self.workloads) - 1)
        self.mark_dirty()
        self.refresh_estimates()
        self.select(self.selected)

    def action_save(self):
        try:
            save_workloads(self.path, self.workloads, self.settings)
        except OSError as e:
            self.notify(f"Couldn't save to {self.path}: {e}", severity="error")
            return
        self.dirty = False
        saved = len(self.workloads)
        self.notify(f"Saved {saved} workload{'s' if saved != 1 else ''} to {self.path}")

    async def action_quit(self):
        if self.dirty and not self.quit_warned:
            self.quit_warned = True
            self.notify(
                "You have unsaved changes. Press ctrl+s to save, or ctrl+q again to quit.",
                severity="warning",
            )
            return
        self.exit()

    def summary_table(self):
        efficiency = self.settings.packing_efficiency()
        results = [
            estimate_workload(self.instance_types, workload, efficiency)
            for workload in self.workloads
        ]
        costs = [all_model_costs(data, efficiency) for data, _ in results]
        table = Table(
            *(label for _, label in COLUMNS),
            title=f"Workloads {model_label(self.settings.cost_model, efficiency)}",
            caption=total_text(costs, self.settings),
        )
        for workload, (_, error), workload_costs in zip(
            self.workloads, results, costs, strict=True
        ):
            table.add_row(
                *row_cells(
                    workload,
                    error,
                    workload_costs and workload_costs[self.settings.cost_model],
                )
            )
        return table
