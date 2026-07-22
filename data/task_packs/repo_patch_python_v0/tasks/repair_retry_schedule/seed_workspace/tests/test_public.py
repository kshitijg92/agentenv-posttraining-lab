from retry import retry_delays


def test_builds_small_capped_schedule() -> None:
    assert retry_delays(2.0, 2.0, 5, 10.0) == [2.0, 4.0, 8.0, 10.0, 10.0]
