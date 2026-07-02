from __future__ import annotations

from .common import RugbySourceAdapter, ScrapeContext, SourceConfig

CONFIG = SourceConfig(
    source_name="theanalyst.com",
    domains=("theanalyst.com", "www.theanalyst.com"),
    search_templates=(
        "https://theanalyst.com/club-rugby-stats/?s={query}",
        "https://theanalyst.com/search/?q={query}",
        "https://theanalyst.com/?s={query}",
    ),
)

_ADAPTER = RugbySourceAdapter(CONFIG)


def set_context(context: ScrapeContext) -> None:
    _ADAPTER.set_context(context)


def find_player_position(player_name: str, country: str):
    return _ADAPTER.find_player_position(player_name, country)

