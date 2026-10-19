"""Pure topology input helpers for the #255 real Docker scenario."""
from dataclasses import replace


def with_nodes(graph, values):
    """Existing construction moved here before the containment-law correction."""
    return replace(graph, nodes=values, runtimes={"docker":
        replace(graph.runtimes["docker"], children=tuple(values))})
