import json
import textwrap

import click

SCROOGE = r'''
           \
            \       _.-""""-._
             \    .'          `-._
                 /                `-._
                /  .------------.     `-.
               |  /              \       (@)
               | |   ___    ___   |
               | |  ( o )--( o )  |
              (| |       \        |)
              (| |        \       |)       )
               \\|       __)      |/      (
                \|                |      (_)
                 |     .----.     |      |=|
                 |    /      \    |      |=|
                  \              /     __|=|__
                   `-.________.-'     (_______)
'''.strip("\n")

# Scrooge's mood by the whole-node monthly cost: the cost it's for (up to, but not
# including), his opening words, and his parting words
MOODS = [
    (
        1000,
        "Hmph. A trifle, I grant thee, but a trifle is still a coin out of my purse.",
        "Spend it, then, and begone! I have a counting-house to keep.",
    ),
    (
        100000,
        "Bah! Humbug! Thou comest to me with thy hand out again?",
        "Every penny, mark me! Every last penny!",
    ),
    (
        float("inf"),
        "BAH! HUMBUG! Wouldst thou see me in the poorhouse?",
        "Are there no prisons? Are there no workhouses? Shrink it, I say, shrink it!",
    ),
]


def render(format, data):
    if format == "english":
        render_english(data)
    elif format == "json":
        render_json(data)
    elif format == "scrooge":
        render_scrooge(data)
    else:
        raise ValueError(f"Unknown format: {format}")


def render_english(data):
    click.echo(
        f"This workload is running on {data['instance']} instances in {data['region']} with {data['instance_specs']['cores']} cores and {data['instance_specs']['memory']}GiB of memory."
    )
    click.echo(
        f"This workload will require {data['delta_cpu'] / 1000} cores and {data['delta_mem'] / 1024} GiB of memory. This workload is {data['constrained_resource']}-constrained."
    )
    click.echo(
        f"This workload will require {data['required_instance_count']} instances, costing ${data['costs']['hourly']}/h (or ${data['costs']['monthly']}/m (or ${data['costs']['yearly']}/y)) at {data['costs']['class']} rates."
    )
    resource_costs = data["resource_costs"]
    if resource_costs:
        click.echo(
            f"Bin-packed in a cluster at {efficiency_text(data['packing_efficiency'])}, this workload will cost ${resource_costs['total']['hourly']}/h (or ${resource_costs['total']['monthly']}/m (or ${resource_costs['total']['yearly']}/y)): ${resource_costs['cores']['monthly']}/m for cores and ${resource_costs['memory']['monthly']}/m for memory."
        )
    else:
        click.echo(
            f"skrooge can't split {data['instance']} pricing into cores and memory, so there's no bin-packed estimate."
        )


def efficiency_text(packing_efficiency):
    cores, memory = packing_efficiency["cores"], packing_efficiency["memory"]
    if cores == memory:
        return f"{cores}% efficiency"
    return f"{cores}% CPU and {memory}% memory efficiency"


def render_json(data):
    click.echo(json.dumps(data))


def render_scrooge(data):
    click.echo(speech_bubble(scrooge_speech(data)))
    click.echo(SCROOGE)


def scrooge_speech(data):
    "What Scrooge has to say about the estimate, as a list of paragraphs"
    costs = data["costs"]
    opening, closing = next(
        (opening, closing)
        for up_to, opening, closing in MOODS
        if costs["monthly"] < up_to
    )
    replicas = data["replicas"]
    nodes = data["required_instance_count"]
    cores = data["delta_cpu"] / 1000
    speech = [
        opening,
        f"Thy {replicas:,} {plural(replicas, 'replica')} upon {data['instance']} in {data['region']} {'doth' if replicas == 1 else 'do'} want {number(cores)} {plural(cores, 'core')} and {number(data['delta_mem'] / 1024)} GiB of memory, and 'tis the {data['constrained_resource']} that bindeth thee.",
        f"{nodes:,} whole {plural(nodes, 'node')} thou must have, at {costs['class']} rates: {coins(costs['hourly'], 2)} the hour, {coins(costs['monthly'])} the month, and {coins(costs['yearly'])} the year!",
    ]
    resource_costs = data["resource_costs"]
    if resource_costs:
        total = resource_costs["total"]
        speech.append(
            f"Packed as tight as the coins in my strongbox, at {efficiency_text(data['packing_efficiency'])}, 'twould be {coins(total['monthly'])} the month and {coins(total['yearly'])} the year."
        )
    else:
        speech.append(
            f"Nor will I split {data['instance']}'s price into cores and memory, so thou gettest no cheaper reckoning from me."
        )
    speech += [
        "And if thou art shrinking it, these be thy savings, and the first good news I have had all day.",
        closing,
    ]
    return speech


def speech_bubble(paragraphs, width=58):
    "A speech bubble around the paragraphs, wrapped to width, with a line between each"
    lines = []
    for paragraph in paragraphs:
        if lines:
            lines.append("")
        lines += textwrap.wrap(paragraph, width)
    inner = max(len(line) for line in lines)
    bubble = [" " + "_" * (inner + 2)]
    for i, line in enumerate(lines):
        if len(lines) == 1:
            left, right = "<", ">"
        elif i == 0:
            left, right = "/", "\\"
        elif i == len(lines) - 1:
            left, right = "\\", "/"
        else:
            left, right = "|", "|"
        bubble.append(f"{left} {line.ljust(inner)} {right}")
    bubble.append(" " + "-" * (inner + 2))
    return "\n".join(bubble)


def plural(count, word):
    return word if count == 1 else f"{word}s"


def number(amount):
    "An amount with up to two decimal places, without trailing zeros"
    return f"{amount:,.2f}".rstrip("0").rstrip(".")


def coins(amount, decimals=0):
    return f"${amount:,.{decimals}f}"
