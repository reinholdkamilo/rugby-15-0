# Rugby 15-0

## Import Rugby World Cup Squads

```bash
cd backend
source .venv/bin/activate
python -m app.import_squads
```

## Import All Rugby World Cups

```bash
cd backend
source .venv/bin/activate
python -m app.importers.import_all
```

## Audit Imported Data

```bash
cd backend
source .venv/bin/activate
python -m app.importers.audit
```

The audit writes `reports/data_quality_audit.json`.

## Audit Positions

```bash
cd backend
source .venv/bin/activate
python -m app.importers.position_audit
```

The position audit writes:

- `reports/position_audit.json`
- `reports/position_corrections_template.csv`

To apply manual corrections, copy rows into `reports/position_corrections.csv`, fill
`suggested_position`, then run:

```bash
python -m app.importers.apply_position_corrections
```

## Infer Positions

```bash
cd backend
source .venv/bin/activate
python -m app.importers.infer_positions --dry-run
python -m app.importers.infer_positions
```

The inference command fills TBC squad positions from repeated player history and
writes `reports/position_inference_report.json`.

## Enrich TBC Positions From Public Sources

```bash
cd backend
source .venv/bin/activate
python -m app.importers.enrich_tbc_positions --dry-run
python -m app.importers.enrich_tbc_positions
```

The enrichment command targets only `TBC` squad appearances, checks
Wikidata/Wikipedia structured data where available, updates high-confidence
positions, and leaves uncertain cases in `reports/tbc_position_review.csv` for
manual review. It writes `reports/tbc_position_enrichment_report.json`.

## Scrape Trusted Rugby Profile Sites

```bash
cd backend
source .venv/bin/activate
python -m app.importers.scrape_tbc_positions --dry-run --limit 50
python -m app.importers.scrape_tbc_positions --limit 200
```

The scraper checks only deduplicated `TBC` players, caches search results and
profile pages under `backend/cache/position_scrape`, and writes:

- `reports/tbc_position_scrape_report.json`
- `reports/tbc_position_scrape_review.csv`

It uses trusted rugby profile sources where available and only updates
high-confidence matches.

## Apply Player Position Dictionary

```bash
cd backend
source .venv/bin/activate
python -m app.importers.apply_player_position_dictionary
```

The dictionary command reads `../data/reference/player_positions.csv`, updates only
TBC squad positions, syncs spin-pool eligible positions, and writes
`reports/player_position_dictionary_report.json`.

## Build Player Aliases

```bash
cd backend
source .venv/bin/activate
python -m app.importers.build_aliases
```

The alias builder creates exact, lowercase, accent-stripped,
punctuation-stripped, and initial-based aliases for every player. It writes
`reports/player_alias_report.json` and is safe to rerun.

## Detect and Merge Duplicate Players

```bash
cd backend
source .venv/bin/activate
python -m app.importers.detect_duplicates
```

Duplicate detection is report-only. It writes:

- `reports/duplicate_detection_report.json`
- `reports/player_merge_template.csv`

To apply approved manual merges, copy reviewed rows into
`reports/player_merges.csv`, set `approved` to `true`, `yes`, or `1`, then run:

```bash
python -m app.importers.apply_player_merges
```

The merge command reassigns squad appearances, ratings, draft picks, and aliases
before deleting the merged source player. It writes
`reports/player_merge_report.json`.

## Import Starter Ratings

```bash
cd backend
source .venv/bin/activate
python -m app.importers.import_ratings
```

The rating importer reads `../data/ratings/rating_seed.csv`, matches rows by
player and country, attaches year-specific ratings to squad appearances when
possible, and creates player-level ratings when year is blank. It writes
`reports/rating_import_report.json` and is idempotent.

## Generate Baseline Ratings

```bash
cd backend
source .venv/bin/activate
python -m app.importers.generate_ratings
python -m app.importers.generate_ratings --overwrite-generated-only
```

The generator creates deterministic baseline ratings for squad appearances that
do not already have manual ratings. Generated rows use
`Generated Baseline v1`; manual seed ratings keep `Manual Seed`. The overwrite
flag recalculates only generated rows and still preserves manual ratings. The
report is written to `reports/generated_ratings_report.json`.

## Phase A Database QA

```bash
cd backend
source .venv/bin/activate
python -m app.importers.phase_a_check
```

The Phase A check summarises import validation, data audit, position audit,
alias coverage, duplicate candidates, rating status, and database counts. It
writes `reports/phase_a_check.json`.

Rating admin helpers:

```text
POST /admin/ratings/generate
POST /admin/ratings/generate?overwrite_generated_only=true
GET /admin/rating-summary
```

## Test Spin API

```text
http://127.0.0.1:8000/spin
http://127.0.0.1:8000/spin?country=New%20Zealand
http://127.0.0.1:8000/spin?year_min=2019&year_max=2019&position=FH
```

## Test Draft API

```bash
curl -X POST http://127.0.0.1:8000/draft-sessions
curl http://127.0.0.1:8000/draft-sessions/1
curl -X POST http://127.0.0.1:8000/draft-sessions/1/picks \
  -H "Content-Type: application/json" \
  -d '{"squad_appearance_id":1,"selected_position":"FH"}'
curl http://127.0.0.1:8000/draft-sessions/1/rating
curl -X POST http://127.0.0.1:8000/draft-sessions/1/simulate
```
