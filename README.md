# healthy

Download Garmin Connect activities from the command line and optionally run the download automatically after your Mac wakes from sleep.

## Quick start

```bash
./install.sh
healthy auth login
healthy activities download
```

`healthy auth login` stores Garmin tokens in `~/.garminconnect` by default. Your Garmin password is only used for login.

## Install

Install the `healthy` command into `~/.local/bin`:

```bash
./install.sh
healthy --help
```

If `healthy` is not found after install, add this to your shell profile:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

For local development without installing:

```bash
uv sync
uv run healthy --help
```

## Sign in to Garmin

```bash
healthy auth login
```

Optional non-interactive inputs:

```bash
GARMIN_EMAIL='you@example.com' healthy auth login
GARMIN_EMAIL='you@example.com' GARMIN_PASSWORD='...' healthy auth login
```

## Download activities

Run an incremental download:

```bash
healthy activities download
```

By default, activities are read newest-first and the sync stops at the first activity already found in local storage.

Default storage location:

```text
~/Documents/Activities
```

Download every missing activity instead of stopping at the first local one:

```bash
healthy activities download --all-missing
```

Use a different output directory:

```bash
healthy activities download --output-dir ~/Documents/Garmin
```

Download a specific format:

```bash
healthy activities download --format gpx
```

Supported formats:

```text
original, gpx, tcx, kml, csv
```

Compress stored activity files with XZ:

```bash
healthy activities download --storage-compression xz
```

Filter by activity type:

```bash
healthy activities download --type running
```

Limit how many remote activities are inspected:

```bash
healthy activities download --max-activities 50
```

## Auto-run after wake on macOS

Install a user LaunchAgent that checks for wake gaps and runs the downloader after the Mac was asleep/away longer than the threshold:

```bash
healthy autorun install --sleep-threshold-minutes 30 --network-timeout-minutes 10
```

Behavior:

- normal per-minute checks exit silently
- after a long sleep/wake gap, `healthy` waits briefly for network availability
- then it runs `activities download`
- only the final result notification is shown

Example notifications:

```text
Downloaded 3 new activities at 2026-08-10 14:32
No new Garmin activity at 2026-08-10 14:32
Garmin auth expired — run healthy auth login
healthy auto-run failed — see log
```

Check status:

```bash
healthy autorun status
```

Uninstall auto-run:

```bash
healthy autorun uninstall
```

Auto-run files:

```text
~/Library/LaunchAgents/net.wygoda.healthy.autorun.plist
~/Library/Application Support/healthy/autorun-state.json
~/Library/Logs/healthy/autorun.log
```

## Garmin rate limiting

The downloader is deliberately conservative:

- waits at least `--request-delay` seconds between Garmin API requests, default `1.0`
- retries Garmin 429/rate-limit responses with exponential backoff
- stops instead of hammering Garmin when the retry budget is exhausted
- stops at the first local activity by default, minimizing normal incremental runs

Tune rate limiting:

```bash
healthy activities download \
  --request-delay 2 \
  --rate-limit-retries 6 \
  --rate-limit-initial-backoff 120 \
  --rate-limit-max-backoff 1800
```

## Troubleshooting

If downloads fail because auth expired:

```bash
healthy auth login
```

If auto-run did not fire, check:

```bash
healthy autorun status
cat ~/Library/Logs/healthy/autorun.log
```

If the installed command points at old code, reinstall:

```bash
./install.sh
healthy autorun uninstall
healthy autorun install
```

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md).
