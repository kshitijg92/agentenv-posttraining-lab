from relative_path import normalize_relative_path


def test_removes_dot_and_duplicate_separators() -> None:
    assert normalize_relative_path("reports/./daily//summary.txt") == (
        "reports/daily/summary.txt"
    )
