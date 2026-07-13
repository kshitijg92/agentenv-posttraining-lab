from header_tools import merge_headers


def test_exact_name_override_and_new_header() -> None:
    result = merge_headers(
        {"Accept": "application/json", "User-Agent": "base"},
        {"User-Agent": "custom", "X-Request-ID": "r1"},
    )

    assert result == {
        "Accept": "application/json",
        "User-Agent": "custom",
        "X-Request-ID": "r1",
    }
