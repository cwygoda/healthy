# healthy

CLI-driven Garmin Connect activity downloader using a small hexagonal architecture.

## Install / run

```bash
uv sync
uv run healthy --help
```

To install the `healthy` command globally:

```bash
./install.sh
healthy --help
```

## Authenticate

```bash
uv run healthy auth login
```

Credentials are used only to obtain Garmin tokens via `garminconnect`; tokens are stored in `~/.garminconnect` by default.

## Download activities

```bash
uv run healthy activities download
```

By default, activities are read newest-first and the sync stops at the first activity already found in local storage (`~/Document/Activities`). To scan past existing activities and fetch every missing one:

```bash
uv run healthy activities download --all-missing
```

Useful options:

- `--output-dir PATH` local activity storage directory
- `--format original|gpx|tcx|kml|csv` download format (`original` saves Garmin's ZIP)
- `--storage-compression none|xz` optionally store activity files compressed with XZ (`original` extracts Garmin's ZIP and stores the contained FIT as `.fit.xz`)
- `--max-activities N` cap how many remote activities are inspected
- `--type running` filter by Garmin activity type
- `--tokenstore PATH` Garmin token directory

## Garmin rate limiting

The downloader is deliberately conservative:

- waits at least `--request-delay` seconds between Garmin API requests (default: `1.0`)
- retries Garmin 429/rate-limit responses with exponential backoff (default: `60s`, `120s`, `240s`, capped at `900s`)
- stops the sync instead of continuing to hammer Garmin if the retry budget is exhausted
- still stops at the first local activity by default, minimizing API calls on normal incremental runs

Tune with:

```bash
uv run healthy activities download \
  --request-delay 2 \
  --rate-limit-retries 6 \
  --rate-limit-initial-backoff 120 \
  --rate-limit-max-backoff 1800
```
