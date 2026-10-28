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

MCDUCK = r"""
           \
            \               _______
             \             |       |
                           |       |
                         __|_______|__
                          /         \
                         /  (o)      \
                  ______/   /         |~~
                 (______    (         |~~~
                  \_____`.   \        /~~
                         `-----.____.'
                  _          /  >o<  \
                 ( `.       /    |    \
                     |-----|     |     |
                     |      \    o    /
                     |       \   |   /
                     |        |  o  |
                     |        |__|__|
                     |         |   |
                     |      ___|  _|
                     |     <___| <__|
""".strip("\n")

# Each character's mood by the whole-node monthly cost: the cost it's for (up to, but
# not including), their opening words, and their parting words
SCROOGE_MOODS = [
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
MCDUCK_MOODS = [
    (
        1000,
        "Och, a wee sum, I'll grant ye. But I didnae make me fortune by tossin' wee sums aboot!",
        "Mind ye, a penny saved is a penny I keep. Now off wi' ye!",
    ),
    (
        100000,
        "Bless me bagpipes! Ye want HOW much?",
        "Be tougher than the toughies and smarter than the smarties, and ye'll no' need sae many nodes!",
    ),
    (
        float("inf"),
        "Curse me kilts! That's enough tae drain me money bin!",
        "I'll be divin' intae me money bin tae count what's left. Shrink it, ye scallywag!",
    ),
]


def render(format, data):
    if format == "english":
        render_english(data)
    elif format == "json":
        render_json(data)
    elif format == "scrooge":
        render_scrooge(data)
    elif format == "mcduck":
        render_mcduck(data)
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
    render_character(scrooge_speech(data), SCROOGE)


def render_mcduck(data):
    render_character(mcduck_speech(data), MCDUCK)


def render_character(speech, art):
    click.echo(speech_bubble(speech))
    click.echo(art)


def spoken(data):
    "The estimate's amounts, as a character says them"
    costs = data["costs"]
    resource_costs = data["resource_costs"]
    return {
        "replicas": f"{data['replicas']:,}",
        "nodes": f"{data['required_instance_count']:,}",
        "cores": number(data["delta_cpu"] / 1000),
        "memory": number(data["delta_mem"] / 1024),
        "hourly": coins(costs["hourly"], 2),
        "monthly": coins(costs["monthly"]),
        "yearly": coins(costs["yearly"]),
        # The bin-packed costs, if there are any
        "packed": resource_costs
        and {
            period: coins(resource_costs["total"][period])
            for period in ("monthly", "yearly")
        },
    }


def mood(moods, data):
    "A character's opening and parting words for the estimate"
    return next(
        (opening, closing)
        for up_to, opening, closing in moods
        if data["costs"]["monthly"] < up_to
    )


def scrooge_speech(data):
    "What Scrooge has to say about the estimate, as a list of paragraphs"
    opening, closing = mood(SCROOGE_MOODS, data)
    said = spoken(data)
    replicas, nodes, cores = said["replicas"], said["nodes"], said["cores"]
    speech = [
        opening,
        f"Thy {replicas} {plural(replicas, 'replica')} upon {data['instance']} in {data['region']} {'doth' if replicas == '1' else 'do'} want {cores} {plural(cores, 'core')} and {said['memory']} GiB of memory, and 'tis the {data['constrained_resource']} that bindeth thee.",
        f"{nodes} whole {plural(nodes, 'node')} thou must have, at {data['costs']['class']} rates: {said['hourly']} the hour, {said['monthly']} the month, and {said['yearly']} the year!",
    ]
    if said["packed"]:
        speech.append(
            f"Packed as tight as the coins in my strongbox, at {efficiency_text(data['packing_efficiency'])}, 'twould be {said['packed']['monthly']} the month and {said['packed']['yearly']} the year."
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


def mcduck_speech(data):
    "What Scrooge McDuck has to say about the estimate, as a list of paragraphs"
    opening, closing = mood(MCDUCK_MOODS, data)
    said = spoken(data)
    replicas, nodes, cores = said["replicas"], said["nodes"], said["cores"]
    speech = [
        opening,
        f"Yer {replicas} {plural(replicas, 'replica')} on {data['instance']} in {data['region']} {'wants' if replicas == '1' else 'want'} {cores} {plural(cores, 'core')} and {said['memory']} GiB o' memory, and it's the {data['constrained_resource']} that's got ye by the sporran.",
        f"That's {nodes} whole {plural(nodes, 'node')} at {data['costs']['class']} rates: {said['hourly']} an hour, {said['monthly']} a month, and {said['yearly']} a year!",
    ]
    if said["packed"]:
        speech.append(
            f"Packed as tight as the coins in me money bin, at {efficiency_text(data['packing_efficiency'])}, it'd be {said['packed']['monthly']} a month and {said['packed']['yearly']} a year."
        )
    else:
        speech.append(
            f"I cannae split {data['instance']}'s price intae cores and memory, so there's nae cheaper sum for ye."
        )
    speech += [
        "And if ye're shrinkin' it, those are yer savings, and that's music tae me ears!",
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


def plural(amount, word):
    "The word for the amount, as printed, so it matches when the amount was rounded"
    return word if str(amount) == "1" else f"{word}s"


def number(amount):
    "An amount with up to two decimal places, without trailing zeros"
    return f"{amount:,.2f}".rstrip("0").rstrip(".")


def coins(amount, decimals=0):
    return f"${amount:,.{decimals}f}"
