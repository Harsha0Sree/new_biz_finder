"""The source registry. One adapter module per source."""

from __future__ import annotations

from types import ModuleType

from scanner.sources import producthunt, startups_gallery, techcrunch, yc

ADAPTERS: dict[str, ModuleType] = {
    techcrunch.SOURCE: techcrunch,
    startups_gallery.SOURCE: startups_gallery,
    yc.SOURCE: yc,
    producthunt.SOURCE: producthunt,
}


def get_adapter(source: str) -> ModuleType:
    """The adapter module for a source name."""
    try:
        return ADAPTERS[source]
    except KeyError:
        raise KeyError(f"no adapter for source {source!r}") from None
