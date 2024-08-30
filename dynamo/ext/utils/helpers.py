def truncate_string(
    string: str, max_len: int = 50, placeholder: str = "Nothing provided"
) -> str:
    """Truncate a string to a maximum length of `max_len`

    Example:
        Very very very long text way over the max yada yada yada
        -> Very very very long text way over the max...

    Args:
        description (str): The string to truncate
        max_len (int, optional): Maximum length. Defaults to 50.

    Returns:
        str: The truncated string
    """
    if not string:
        return placeholder
    truncated = string[: max(max_len, len(string) // 2)]
    if len(string) > max_len:
        truncated += "..."
    return truncated
