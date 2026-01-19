"""Creator Agent tools for document generation."""

from langchain_core.tools import tool


@tool
async def generate_document(
    content: str,
    format: str = "markdown",
    title: str = "Report",
) -> str:
    """Generate a formatted document.

    Args:
        content: Content to include in document
        format: Output format (markdown, html)
        title: Document title

    Returns:
        Formatted document string.
    """
    if format == "html":
        return f"""<!DOCTYPE html>
<html>
<head><title>{title}</title></head>
<body>
<h1>{title}</h1>
{content}
</body>
</html>"""
    else:
        return f"# {title}\n\n{content}"
