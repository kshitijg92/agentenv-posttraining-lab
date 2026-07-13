def expand_template(template: str, values: dict[str, str]) -> str:
    """Expand named placeholders in a template."""
    result = template
    for name, value in values.items():
        result = result.replace("${" + name + "}", value)
    return result
