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
    REGIONS,
    InstanceNotFoundError,
    PricingNotFoundError,
    calculate_cost,
    calculate_estimate,
    find_instance_data,
    hourly_price,
    instance_names,
    load_instance_types,
)

NUMERIC_FIELDS = ("replicas", "cpu", "mem")

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


@dataclass
class Workload:
    # Numeric fields hold the text as typed so partial input survives switching
    # between workloads; estimate_workload() parses and validates them.
    name: str = "workload-1"
    replicas: str = "10"
    cpu: str = "1000"
    mem: str = "2048"
    instance: str = "n2-standard-32"
    region: str = "us-central1"
    cost_class: str = "sud"

    def __post_init__(self):
        self.key = f"workload-{next(_keys)}"

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):
            raise TypeError("each workload must be an object")
        unknown = data.keys() - {f.name for f in fields(cls)}
        if unknown:
            raise ValueError(f"unknown workload fields: {', '.join(sorted(unknown))}")
        workload = cls(**{name: str(value) for name, value in data.items()})
        if workload.region not in REGIONS:
            raise ValueError(f"unknown region: {workload.region}")
        if workload.cost_class not in COST_CLASSES:
            raise ValueError(f"unknown cost class: {workload.cost_class}")
        return workload

    def to_dict(self):
        data = asdict(self)
        for name in NUMERIC_FIELDS:
            value = parse_int(data[name])
            if value is not None:
                data[name] = value
        return data


def load_workloads(path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        workloads = data["workloads"]
    except (TypeError, KeyError):
        raise TypeError('expected an object with a "workloads" list') from None
    if not isinstance(workloads, list):
        raise TypeError('expected an object with a "workloads" list')
    return [Workload.from_dict(workload) for workload in workloads]


def save_workloads(path, workloads):
    data = {"workloads": [workload.to_dict() for workload in workloads]}
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def parse_int(value):
    try:
        return int(value)
    except ValueError:
        return None


def estimate_workload(instance_types, workload):
    "Returns (data, error), exactly one of which is None"
    replicas = parse_int(workload.replicas)
    if replicas is None or replicas < 0:
        return None, "Replicas must be a whole number, 0 or more."
    cpu = parse_int(workload.cpu)
    if cpu is None:
        return None, "CPU change must be a whole number of milli-cores."
    mem = parse_int(workload.mem)
    if mem is None:
        return None, "Memory change must be a whole number of MiB."
    instance = workload.instance.strip().lower()
    if not instance:
        return None, "Enter an instance type."
    try:
        data = calculate_estimate(
            instance_types,
            instance,
            replicas,
            cpu,
            mem,
            cost_class=workload.cost_class,
            region=workload.region,
        )
    except (InstanceNotFoundError, PricingNotFoundError) as e:
        return None, str(e)
    return data, None


def direction(data):
    "-1 if the workload shrinks the resource it's bound by (a saving), else 1"
    change = data["cpu"] if data["constrained_resource"] == "cores" else data["mem"]
    return -1 if change < 0 else 1


def quantity(amount):
    return f"{amount:,.2f}".rstrip("0").rstrip(".")


def money(amount, decimals=0):
    sign = "-" if amount < 0 else ""
    return f"{sign}${abs(amount):,.{decimals}f}"


def row_cells(workload, data, error):
    cells = [
        workload.name or "(unnamed)",
        workload.replicas,
        workload.cpu,
        workload.mem,
        workload.instance,
        workload.region,
        workload.cost_class,
    ]
    if error:
        return [*cells, Text("⚠ invalid", style="bold red"), "", ""]
    sign = direction(data)
    style = "green" if sign < 0 else ""
    costs = data["costs"]
    return [
        *cells,
        Text(str(sign * data["required_instance_count"]), style, justify="right"),
        Text(money(sign * costs["monthly"]), style, justify="right"),
        Text(money(sign * costs["yearly"]), style, justify="right"),
    ]


def total_text(results):
    estimates = [data for data, _ in results if data]
    hourly, monthly, yearly = (
        sum(direction(data) * data["costs"][period] for data in estimates)
        for period in ("hourly", "monthly", "yearly")
    )
    text = Text.assemble(
        ("Net change: ", "bold"),
        (f"{money(hourly, 2)}/h · {money(monthly)}/mo · {money(yearly)}/yr", "bold"),
        f" across {len(estimates)} workload{'s' if len(estimates) != 1 else ''}",
    )
    invalid = len(results) - len(estimates)
    if invalid:
        text.append(
            f"  ⚠ {invalid} workload{'s' if invalid != 1 else ''} with invalid inputs not included",
            "bold red",
        )
    return text


def labelled(label, widget):
    return Horizontal(Label(label), widget, classes="field")


class SkroogeApp(App):
    TITLE = "skrooge"
    SUB_TITLE = "Kubernetes scaling cost estimator"
    CSS = """
    #top {
        height: auto;
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
    .hint {
        margin-top: 1;
        color: $text-muted;
    }
    #tiers {
        height: auto;
        margin-top: 1;
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
        Binding("ctrl+s", "save", "Save", priority=True),
    )

    def __init__(self, workloads, path, instance_types=None):
        super().__init__()
        self.instance_types = instance_types or load_instance_types()
        self.workloads = list(workloads) or [Workload()]
        self.path = path
        self.selected = 0
        self.results = []
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
                yield labelled(
                    "Replicas",
                    Input(
                        first.replicas,
                        id="replicas",
                        type="integer",
                        validators=[Integer(minimum=0)],
                        compact=True,
                    ),
                )
                yield labelled(
                    "CPU Δ (m)",
                    Input(first.cpu, id="cpu", type="integer", compact=True),
                )
                yield labelled(
                    "Memory Δ (MiB)",
                    Input(first.mem, id="mem", type="integer", compact=True),
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
                        [(region, region) for region in REGIONS],
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
                yield Static(
                    "CPU and memory are per replica. Negative values scale "
                    "down (savings).",
                    classes="hint",
                )
            with Vertical(id="estimate"):
                yield Static(id="summary")
                yield DataTable(id="tiers", cursor_type="none")
        yield DataTable(id="table", cursor_type="row", zebra_stripes=True)
        yield Static(id="total")
        yield Footer()

    def on_mount(self):
        self.query_one("#inputs").border_title = "Inputs"
        self.query_one("#table").border_title = "Workloads"
        tiers = self.query_one("#tiers", DataTable)
        tiers.can_focus = False
        tiers.add_column("Cost class")
        for label in ("$/node/h", "$/hour", "$/month", "$/year"):
            tiers.add_column(Text(label, justify="right"))
        table = self.query_one("#table", DataTable)
        for key, label in COLUMNS:
            table.add_column(label, key=key)
        self.refresh_estimates()
        self.select(0)

    def refresh_estimates(self):
        self.results = [
            estimate_workload(self.instance_types, workload)
            for workload in self.workloads
        ]
        table = self.query_one("#table", DataTable)
        for workload, (data, error) in zip(self.workloads, self.results, strict=True):
            cells = row_cells(workload, data, error)
            if workload.key in table.rows:
                for (column, _), cell in zip(COLUMNS, cells, strict=True):
                    table.update_cell(workload.key, column, cell, update_width=True)
            else:
                table.add_row(*cells, key=workload.key)
        self.query_one("#total", Static).update(total_text(self.results))
        self.show_estimate()

    def show_estimate(self):
        workload = self.workloads[self.selected]
        data, error = self.results[self.selected]
        self.query_one(
            "#estimate"
        ).border_title = f"Estimate · {workload.name or '(unnamed)'}"
        try:
            instance_data = find_instance_data(
                self.instance_types, workload.instance.strip().lower()
            )
        except InstanceNotFoundError:
            instance_data = None

        if error:
            summary = Text(error, "red")
        else:
            specs = data["instance_specs"]
            sign = direction(data)
            summary = Text.assemble(
                (data["instance"], "bold"),
                f": {specs['cores']} cores, {specs['memory']} GiB per node\n",
                f"Needs {quantity(data['delta_cpu'] / 1000)} cores and "
                f"{quantity(data['delta_mem'] / 1024)} GiB in total "
                f"({'CPU' if data['constrained_resource'] == 'cores' else 'memory'}-bound)\n",
                (
                    (
                        f"{'Frees' if sign < 0 else 'Adds'} "
                        f"{data['required_instance_count']} node"
                        f"{'s' if data['required_instance_count'] != 1 else ''}"
                    ),
                    "bold green" if sign < 0 else "bold",
                ),
            )
        self.query_one("#summary", Static).update(summary)

        tiers = self.query_one("#tiers", DataTable)
        tiers.clear()
        for cost_class in COST_CLASSES:
            current = cost_class == workload.cost_class
            label = Text(
                f"{'▶' if current else ' '} {cost_class}", "bold" if current else ""
            )
            price = (
                hourly_price(instance_data, cost_class, workload.region)
                if instance_data
                else None
            )
            if price is None:
                cells = ["n/a", "", "", ""]
            elif data is None:
                cells = [money(price, 2), "—", "—", "—"]
            else:
                sign = direction(data)
                costs = calculate_cost(
                    instance_data,
                    data["required_instance_count"],
                    cost_class=cost_class,
                    region=workload.region,
                )
                cells = [
                    money(price, 2),
                    money(sign * costs["hourly"], 2),
                    money(sign * costs["monthly"]),
                    money(sign * costs["yearly"]),
                ]
            tiers.add_row(
                label,
                *(
                    Text(cell, "bold" if current else "", justify="right")
                    for cell in cells
                ),
            )

    def select(self, index):
        self.selected = index
        workload = self.workloads[index]
        for name in ("name", "replicas", "cpu", "mem", "instance"):
            self.query_one(f"#{name}", Input).value = getattr(workload, name)
        self.query_one("#region", Select).value = workload.region
        self.query_one("#cost_class", Select).value = workload.cost_class
        self.show_estimate()
        self.query_one("#table", DataTable).move_cursor(row=index)

    def mark_dirty(self):
        self.dirty = True
        self.quit_warned = False

    def update_selected(self, name, value):
        workload = self.workloads[self.selected]
        # Filling in the form in select() also posts Changed events, which may
        # arrive after the selection has moved on. Handlers pass the widget's
        # current value, so those events are no-ops here.
        if getattr(workload, name) == value:
            return
        setattr(workload, name, value)
        self.mark_dirty()
        self.refresh_estimates()

    def on_input_changed(self, event):
        # Only the form's inputs; the command palette's input bubbles up too
        if event.input.parent.has_class("field"):
            self.update_selected(event.input.id, event.input.value)

    def on_select_changed(self, event):
        self.update_selected(event.select.id, event.select.value)

    def on_data_table_row_highlighted(self, event):
        if event.data_table.id != "table":
            return
        # Like the form's events, these can be stale (and select() posts more
        # of them), so follow where the cursor is now
        index = event.data_table.cursor_row
        if index != self.selected and 0 <= index < len(self.workloads):
            self.select(index)

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
            save_workloads(self.path, self.workloads)
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
        results = [
            estimate_workload(self.instance_types, workload)
            for workload in self.workloads
        ]
        table = Table(*(label for _, label in COLUMNS), caption=total_text(results))
        for workload, (data, error) in zip(self.workloads, results, strict=True):
            table.add_row(*row_cells(workload, data, error))
        return table
