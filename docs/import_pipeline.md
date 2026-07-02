# Rugby 15-0 Import Pipeline

The Rugby World Cup import pipeline is designed around offline source files. It
does not scrape live data during development. Source snapshots should be stored
under `data/` and then imported into the existing SQLAlchemy tables.

## Goals

- Support every Rugby World Cup: 1987, 1991, 1995, 1999, 2003, 2007, 2011,
  2015, 2019, and 2023.
- Keep every import idempotent.
- Normalize country, player, position, captain, and replacement data before it
  reaches the database.
- Make it possible to add future competitions without rewriting the importer.

## Package Layout

`backend/app/importers/base_importer.py`

Defines the shared row contracts, import report, and database upsert logic. It
imports normalized rows into `players`, `squad_appearances`, and `spin_pool`.
Ratings are intentionally left empty until a rating source exists.

`backend/app/importers/csv_importer.py`

Reads offline CSV files. Current supported locations are:

- `data/squads/rwc_<year>_squads.csv`
- `data/squads/<year>_squads.csv`
- `data/imports/rwc/*<year>*squad*.csv`

`backend/app/importers/wikipedia_importer.py`

Offline/cache-only adapter for future Wikipedia-derived snapshots. It reads
CSV exports from `data/imports/wikipedia`. It does not fetch live pages.

`backend/app/importers/normaliser.py`

Normalizes:

- player names
- country aliases
- position aliases
- captain values
- replacement-player values
- duplicate spelling keys

`backend/app/importers/validator.py`

Builds a validation report containing:

- players imported
- countries imported
- duplicates detected
- missing positions
- rows skipped
- warnings

`backend/app/importers/import_all.py`

Orchestrates all Rugby World Cup years:

```bash
cd backend
source .venv/bin/activate
python -m app.importers.import_all
```

The command seeds the baseline country, tournament, and position tables first,
then imports any offline squad files available for each World Cup year.

## CSV Contract

Recommended columns:

```text
year,country,player_name,position,secondary_positions,captain,replacement,replacement_for,source_url
```

The existing milestone CSV omits `replacement` and `replacement_for`; those
fields are optional.

## Idempotency

The importer uses stable natural keys:

- player: `display_name + country`
- squad appearance: `player + country + tournament`
- spin pool: `country + tournament`

Running the same import repeatedly updates existing rows instead of inserting
duplicates.

## Future Competitions

Future competitions should add a new source adapter that yields the same
`RawSquadRow` contract. The base importer can then import:

- Six Nations
- The Rugby Championship
- British & Irish Lions
- Super Rugby
- URC
- Top 14
- Premiership

Competition-specific tournament modeling may need a later schema extension, but
the source, normalization, validation, and reporting layers are already split so
that change is isolated.
