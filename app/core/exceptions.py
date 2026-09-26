class DocMindError(Exception):
    """Base exception for DocMind-Agent."""


class DependencyUnavailableError(DocMindError):
    """Raised when an infrastructure dependency is unavailable."""
