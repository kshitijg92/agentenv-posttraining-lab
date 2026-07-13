from csv_projection import project_csv


def test_projects_unquoted_columns() -> None:
    source = "name,age,city\nAda,36,London\nLinus,54,Helsinki\n"
    assert project_csv(source, ["name", "city"]) == (
        "name,city\nAda,London\nLinus,Helsinki\n"
    )
