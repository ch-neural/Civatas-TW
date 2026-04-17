"""Shared article relevance filtering — used by calibrator and feed_engine.

Soft-fail import: if us_article_filters has been removed, we fall back to an
always-relevant filter (lets everything through). Taiwan workspaces typically
rely on the crawler-level source whitelist, so the per-article filter is
informational.
"""
import logging
logger = logging.getLogger(__name__)

try:
    try:
        from . import us_article_filters as _us_filter  # type: ignore
    except ImportError:
        import us_article_filters as _us_filter  # type: ignore
    _HAS_FILTER = True
except ImportError:
    logger.info("us_article_filters not available; article filter = passthrough")
    _us_filter = None
    _HAS_FILTER = False


def is_relevant_article(
    title: str = "",
    source: str = "",
    summary: str = "",
) -> bool:
    """Return True if the article is likely relevant to social/political simulation."""
    if not _HAS_FILTER or _us_filter is None:
        return True  # No filter loaded → allow everything
    return _us_filter.is_relevant_article(title=title, source=source, summary=summary)
