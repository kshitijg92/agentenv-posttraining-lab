def project_csv(text: str, columns: list[str]) -> str:
    """Return selected CSV columns."""
    lines = text.strip().splitlines()
    header = lines[0].split(",")
    indices = [header.index(column) for column in columns]
    projected = [[row.split(",")[index] for index in indices] for row in lines]
    return "\n".join(",".join(row) for row in projected) + "\n"
