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

Install a user LaunchAgent that runs the downloader when you come back to an awake Mac and the last successful sync has aged past the interval:

```bash
healthy autorun install --sync-interval-minutes 30 --network-timeout-minutes 10
```

Behavior:

- checks run once a minute and exit silently when there is nothing to do
- checks do nothing during DarkWake, the brief maintenance wakes macOS runs every few minutes while the lid is closed
- on a full wake, if the last successful sync is older than the interval, `healthy` waits briefly for network availability
- then it runs `activities download`, holding a power assertion so a re-sleep cannot kill the sync mid-download
- only the final result notification is shown

The interval is measured from the last *successful* sync, so a failed run retries at the next wake instead of being suppressed.

### Keep notifications from piling up

macOS offers no way to dismiss or replace a notification posted through AppleScript, so by default every auto-run leaves another one behind in Notification Center. Install [terminal-notifier](https://github.com/julienXX/terminal-notifier) and `healthy` uses it automatically, replacing the previous notification instead of stacking a new one:

```bash
brew install terminal-notifier
```

The first notification asks for permission — allow notifications for `terminal-notifier` in System Settings → Notifications. Without it installed, notifications still work, they just accumulate.

Example notifications:

```text
Downloaded 3 new activities at 2026-08-10 14:32
No new Garmin activity at 2026-08-10 14:32
Garmin auth expired — run healthy auth login
healthy auto-run failed — see log
```

Check status, including when the last successful sync ran and whether the Mac is currently in a full wake:

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

`autorun status` shows the last successful sync and the current power state. The log only records ticks that decided to sync, so a quiet log means no sync was due. To see the decision for the current moment without downloading:

```bash
healthy autorun tick --dry-run
```

To watch the sleep/wake events autorun reacts to:

```bash
pmset -g log | grep -E "Sleep  |Wake  |DarkWake"
```

If the installed command points at old code, reinstall:

```bash
./install.sh
healthy autorun uninstall
healthy autorun install
```

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md).
