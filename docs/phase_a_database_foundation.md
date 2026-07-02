# Phase A Database Foundation

Phase A completes the backend/database foundation for Rugby 15-0. It covers the
Rugby World Cup squad database, repeatable import tools, data quality reports,
position correction systems, aliasing, duplicate review, rating seeds, and
admin-style review endpoints.

## Built Systems

- Rugby World Cup squad import pipeline for 1987 through 2023.
- Idempotent CSV import framework under `backend/app/importers/`.
- Data quality audit command and JSON report.
- Position audit, manual correction import, inference, and player position
  dictionary support.
- Player alias table and alias generation command.
- Duplicate detection reports and manual merge tooling.
- Expanded rating table with category ratings, status, source, style, and notes.
- Starter rating seed CSV with 50 high-profile Rugby World Cup players.
- Deterministic generated baseline ratings for every squad appearance.
- Admin backend endpoints for players, duplicates, ratings, and data summaries.
- Final Phase A QA command.

## Commands

Run from the backend directory with the virtual environment active:

```bash
cd backend
source .venv/bin/activate
python -m app.importers.import_all
python -m app.importers.audit
python -m app.importers.position_audit
python -m app.importers.infer_positions --dry-run
python -m app.importers.infer_positions
python -m app.importers.apply_player_position_dictionary
python -m app.importers.build_aliases
python -m app.importers.detect_duplicates
python -m app.importers.import_ratings
python -m app.importers.generate_ratings
python -m app.importers.phase_a_check
```

Manual merge workflow:

```bash
python -m app.importers.detect_duplicates
# review reports/player_merge_template.csv
# create reports/player_merges.csv with approved rows
python -m app.importers.apply_player_merges
```

## Admin Endpoints

- `GET /admin/players`
- `GET /admin/players/{player_id}`
- `GET /admin/players/search?query=`
- `PATCH /admin/players/{player_id}`
- `GET /admin/duplicates`
- `GET /admin/ratings`
- `GET /admin/ratings/{player_id}`
- `PATCH /admin/ratings/{rating_id}`
- `POST /admin/ratings/generate`
- `GET /admin/rating-summary`
- `GET /admin/data-quality-summary`

These endpoints do not have authentication yet and should stay local/internal
until an auth layer is added.

## Current Counts

From `python -m app.importers.phase_a_check`:

- Players: 3,889
- Squad appearances: 5,691
- Spin pool records: 5,691
- Player aliases: 12,137
- Ratings: 5,693
- Generated baseline ratings: 5,643
- Manual seed ratings: 50
- Unrated squad appearances: 0
- TBC squad positions: 2,623
- Duplicate candidate groups: 165

Second-pass idempotency checks:

- `python -m app.importers.import_ratings`: 0 created, 50 updated, 0 skipped.
- `python -m app.importers.build_aliases`: 0 created, 12,137 existing.
- `python -m app.importers.generate_ratings`: 0 created, 0 updated on the
  second pass.

## Baseline Rating Generation

`backend/app/rating_generator.py` creates deterministic baseline ratings using:

- Country strength tier.
- Tournament era adjustment.
- Stable player/tournament hash variation.
- Captain adjustment.
- Position-specific attribute templates.

Generated rows use `source = Generated Baseline v1` and
`rating_status = generated`. Manual seed rows use `source = Manual Seed` and are
not overwritten by generation. `TBC` positions receive balanced utility ratings
with `best_position = TBC` and `style = Utility / Unknown`.

## Known Issues

- 2,623 squad appearances still use `TBC`; these need further dictionary,
  inference, or manual correction work.
- Duplicate candidates are review-only. No automatic merges are applied.
- Ratings are complete enough for gameplay, but the generated baseline should be
  replaced with manual or model-informed ratings over time.
- Admin endpoints are intentionally unauthenticated for local database review.

## Next Phase Recommendation

Move into Phase B with rating expansion and gameplay quality:

- Add richer player ratings by tournament and position.
- Review and apply confirmed duplicate player merges.
- Continue reducing `TBC` positions.
- Connect the frontend draft flow to spin, pick, rating, and simulation APIs.
