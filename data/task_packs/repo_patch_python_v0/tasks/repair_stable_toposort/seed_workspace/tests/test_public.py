from dependency_order import stable_toposort


def test_returns_already_ordered_chain() -> None:
    nodes = ["fetch", "parse", "store"]
    dependencies = {"parse": ["fetch"], "store": ["parse"]}
    assert stable_toposort(nodes, dependencies) == nodes
