from semver import compare_semver


def test_compares_simple_major_versions() -> None:
    assert compare_semver("1.2.0", "2.0.0") == -1
    assert compare_semver("2.0.0", "1.2.0") == 1
    assert compare_semver("1.2.0", "1.2.0") == 0
