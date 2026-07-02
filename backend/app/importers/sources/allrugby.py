from __future__ import annotations

from .common import RugbySourceAdapter, ScrapeContext, SourceConfig

CONFIG = SourceConfig(
    source_name="all.rugby",
    domains=("all.rugby",),
    search_templates=(
        "https://all.rugby/search/?q={query}",
        "https://all.rugby/?s={query}",
        "https://all.rugby/search/{query}",
    ),
)

_ADAPTER = RugbySourceAdapter(CONFIG)


def set_context(context: ScrapeContext) -> None:
    _ADAPTER.set_context(context)


def find_player_position(player_name: str, country: str):
    return _ADAPTER.find_player_position(player_name, country)

