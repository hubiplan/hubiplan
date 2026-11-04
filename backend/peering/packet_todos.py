"""Nur ausdrücklich freigegebene Aufgaben; standardmäßig in beiden Richtungen aus."""

from .packets import BOTH, Packet, register


def build(coupling, level):
    from todos.remote import build as build_tasks

    return build_tasks(coupling, level)


def apply(coupling, data):
    from todos.remote import apply as apply_tasks

    return apply_tasks(coupling, data)


register(
    Packet(
        "todos",
        "Aufgaben (ausdrücklich geteilte Inhalte und Erledigungsstand)",
        BOTH,
        build=build,
        apply=apply,
        under_club=True,
    )
)
