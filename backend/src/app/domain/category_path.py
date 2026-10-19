def category_path(value: str) -> str:
    parts = tuple(part.strip() for part in value.split("/"))
    if not parts or any(not part for part in parts) or len(value) > 200:
        raise ValueError("Invalid category path")
    return " / ".join(parts)
