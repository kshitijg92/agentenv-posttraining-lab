from template import expand_template


def test_expands_one_known_placeholder() -> None:
    assert expand_template("Hello, ${name}!", {"name": "Ada"}) == "Hello, Ada!"
