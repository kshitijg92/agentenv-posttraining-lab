import pytest

from dependency_order import stable_toposort


def test_reorders_dependencies_with_stable_ready_ties() -> None:
    nodes = ["deploy", "lint", "test", "build"]
    dependencies = {
        "deploy": ["test"],
        "test": ["build"],
    }
    assert stable_toposort(nodes, dependencies) == [
        "lint",
        "build",
        "test",
        "deploy",
    ]


def test_accepts_generators_and_does_not_mutate_inputs() -> None:
    dependencies = {"c": ["a", "b"]}
    original = {key: values.copy() for key, values in dependencies.items()}
    assert stable_toposort((item for item in ["c", "b", "a"]), dependencies) == [
        "b",
        "a",
        "c",
    ]
    assert dependencies == original


def test_empty_graph_returns_empty_list() -> None:
    assert stable_toposort(iter(()), {}) == []


@pytest.mark.parametrize(
    ("nodes", "dependencies"),
    [
        ("ab", {}),
        (None, {}),
        (["a", "a"], {}),
        ([""], {}),
        ([1], {}),
        (["a"], []),
        (["a"], {"missing": []}),
        (["a"], {"a": ["missing"]}),
        (["a"], {"a": ["a"]}),
        (["a", "b"], {"b": ["a", "a"]}),
        (["a", "b"], {"b": "a"}),
        (["a", "b"], {"a": ["b"], "b": ["a"]}),
    ],
)
def test_invalid_graphs_raise_value_error(nodes: object, dependencies: object) -> None:
    with pytest.raises(ValueError):
        stable_toposort(nodes, dependencies)  # type: ignore[arg-type]
