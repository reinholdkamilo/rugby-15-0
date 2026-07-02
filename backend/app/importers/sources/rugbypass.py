from __future__ import annotations

from .common import RugbySourceAdapter, ScrapeContext, SourceConfig

CONFIG = SourceConfig(
    source_name="rugbypass.com",
    domains=("rugbypass.com", "www.rugbypass.com"),
    search_templates=(
        "https://www.rugbypass.com/?s={query}",
        "https://www.rugbypass.com/search/?q={query}",
        "https://www.rugbypass.com/search/{query}",
    ),
)

_ADAPTER = RugbySourceAdapter(CONFIG)


def set_context(context: ScrapeContext) -> None:
    _ADAPTER.set_context(context)


def find_player_position(player_name: str, country: str):
    return _ADAPTER.find_player_position(player_name, country)

