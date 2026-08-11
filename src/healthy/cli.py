"""Command line adapter for healthy."""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Callable

import typer
from rich.console import Console
from rich.table import Table

from healthy.adapters.garmin import GarminConnectActivityClient
from healthy.adapters.launchd import install_launch_agent, launch_agent_installed, uninstall_launch_agent
from healthy.adapters.notifications import show_macos_notification
from healthy.adapters.power import is_fully_awake, power_assertion
from healthy.adapters.rate_limit import RateLimitPolicy
from healthy.adapters.storage import FileActivityStorage, StorageCompression
from healthy.application import DownloadActivitiesUseCase
from healthy.autorun import (
    AutorunConfig,
    AutorunDecision,
    AutorunStateStore,
    append_log,
    evaluate_autorun_tick,
)
from healthy.domain import Activity, DownloadFormat, DownloadSummary

app = typer.Typer(
    help="Download Garmin Connect activities into local storage.",
    no_args_is_help=True,
)
auth_app = typer.Typer(help="Authenticate against Garmin Connect.", no_args_is_help=True)
activities_app = typer.Typer(help="Work with Garmin activities.", no_args_is_help=True)
autorun_app = typer.Typer(help="Run healthy automatically after wake.", no_args_is_help=True)
app.add_typer(auth_app, name="auth")
app.add_typer(activities_app, name="activities")
app.add_typer(autorun_app, name="autorun")

console = Console()

DEFAULT_TOKENSTORE = Path("~/.garminconnect")
DEFAULT_ACTIVITY_DIR = Path("~/Documents/Activities")
DEFAULT_AUTORUN_STATE = Path("~/Library/Application Support/healthy/autorun-state.json")
DEFAULT_AUTORUN_LOG = Path("~/Library/Logs/healthy/autorun.log")


@auth_app.command("login")
def login(
    email: Annotated[
        str | None,
        typer.Option(
            "--email",
            "-e",
            envvar="GARMIN_EMAIL",
            help="Garmin account email. Can also be set with GARMIN_EMAIL.",
        ),
    ] = None,
    password: Annotated[
        str | None,
        typer.Option(
            "--password",
            "-p",
            envvar="GARMIN_PASSWORD",
            help="Garmin account password. Can also be set with GARMIN_PASSWORD.",
        ),
    ] = None,
    tokenstore: Annotated[
        Path,
        typer.Option(
            "--tokenstore",
            help="Directory where garminconnect stores refreshable auth tokens.",
        ),
    ] = DEFAULT_TOKENSTORE,
    china: Annotated[
        bool,
        typer.Option("--china", help="Use Garmin China endpoints."),
    ] = False,
) -> None:
    """Login to Garmin and persist auth tokens for later commands."""

    if email is None:
        email = typer.prompt("Garmin email")
    if password is None:
        password = typer.prompt("Garmin password", hide_input=True)

    try:
        GarminConnectActivityClient.login(
            tokenstore=tokenstore,
            email=email,
            password=password,
            prompt_mfa=lambda: typer.prompt("Garmin MFA code"),
            is_cn=china,
        )
    except Exception as exc:  # garminconnect raises several auth-specific errors
        console.print(f"[red]Garmin login failed:[/red] {exc}")
        raise typer.Exit(1) from exc

    console.print(f"[green]Logged in.[/green] Tokens stored in {tokenstore.expanduser()}")


@activities_app.command("download")
def download_activities(
    output_dir: Annotated[
        Path,
        typer.Option(
            "--output-dir",
            "-o",
            help="Local activity storage directory.",
        ),
    ] = DEFAULT_ACTIVITY_DIR,
    download_format: Annotated[
        DownloadFormat,
        typer.Option(
            "--format",
            "-f",
            case_sensitive=False,
            help="Activity download format.",
        ),
    ] = DownloadFormat.ORIGINAL,
    all_missing: Annotated[
        bool,
        typer.Option(
            "--all-missing",
            help=(
                "Continue past local activities and fetch every missing activity. "
                "Without this flag, stop at the first local activity."
            ),
        ),
    ] = False,
    page_size: Annotated[
        int,
        typer.Option("--page-size", min=1, help="Garmin API page size."),
    ] = 20,
    request_delay: Annotated[
        float,
        typer.Option(
            "--request-delay",
            min=0.0,
            help="Minimum seconds to wait between Garmin API requests.",
        ),
    ] = 1.0,
    rate_limit_retries: Annotated[
        int,
        typer.Option(
            "--rate-limit-retries",
            min=0,
            help="Number of 429/rate-limit retries before stopping the sync.",
        ),
    ] = 5,
    rate_limit_initial_backoff: Annotated[
        float,
        typer.Option(
            "--rate-limit-initial-backoff",
            min=0.0,
            help="Initial seconds to wait after Garmin returns a rate-limit response.",
        ),
    ] = 60.0,
    rate_limit_max_backoff: Annotated[
        float,
        typer.Option(
            "--rate-limit-max-backoff",
            min=0.0,
            help="Maximum seconds to wait between rate-limit retries.",
        ),
    ] = 900.0,
    max_activities: Annotated[
        int | None,
        typer.Option(
            "--max-activities",
            min=1,
            help="Maximum remote activities to inspect before stopping.",
        ),
    ] = None,
    activity_type: Annotated[
        str | None,
        typer.Option(
            "--type",
            help="Optional Garmin activity type filter, for example running or cycling.",
        ),
    ] = None,
    storage_compression: Annotated[
        StorageCompression,
        typer.Option(
            "--storage-compression",
            case_sensitive=False,
            help="Compress stored activity files.",
        ),
    ] = StorageCompression.NONE,
    tokenstore: Annotated[
        Path,
        typer.Option(
            "--tokenstore",
            help="Directory containing garminconnect auth tokens.",
        ),
    ] = DEFAULT_TOKENSTORE,
    email: Annotated[
        str | None,
        typer.Option(
            "--email",
            envvar="GARMIN_EMAIL",
            help="Optional Garmin email for first-time login. Prefer `healthy auth login`.",
        ),
    ] = None,
    password: Annotated[
        str | None,
        typer.Option(
            "--password",
            envvar="GARMIN_PASSWORD",
            help="Optional Garmin password for first-time login. Prefer `healthy auth login`.",
        ),
    ] = None,
    china: Annotated[
        bool,
        typer.Option("--china", help="Use Garmin China endpoints."),
    ] = False,
) -> None:
    """Download Garmin activities into local storage."""

    try:
        garmin = GarminConnectActivityClient.login(
            tokenstore=tokenstore,
            email=email,
            password=password,
            prompt_mfa=lambda: typer.prompt("Garmin MFA code"),
            is_cn=china,
            rate_limit_policy=RateLimitPolicy(
                request_delay=request_delay,
                max_retries=rate_limit_retries,
                initial_backoff=rate_limit_initial_backoff,
                max_backoff=rate_limit_max_backoff,
            ),
            on_rate_limit_retry=_print_rate_limit_retry,
        )
    except Exception as exc:
        console.print(f"[red]Could not authenticate with Garmin:[/red] {exc}")
        console.print("Run [bold]healthy auth login[/bold] first, or provide --email/--password.")
        raise typer.Exit(1) from exc

    storage = FileActivityStorage(output_dir, compression=storage_compression)
    use_case = DownloadActivitiesUseCase(
        garmin,
        storage,
        on_progress=_print_activity_event,
    )

    summary = use_case.execute(
        download_format=download_format,
        all_missing=all_missing,
        page_size=page_size,
        max_activities=max_activities,
        activity_type=activity_type,
    )
    _print_summary(summary, output_dir.expanduser())

    if summary.failed or summary.rate_limited:
        raise typer.Exit(1)


@autorun_app.command("install")
def install_autorun(
    sync_interval_minutes: Annotated[
        float,
        typer.Option(
            "--sync-interval-minutes",
            "--sleep-threshold-minutes",
            min=1.0,
            help="Minimum age of the last successful sync before autorun fires.",
        ),
    ] = 30.0,
    network_timeout_minutes: Annotated[
        float,
        typer.Option(
            "--network-timeout-minutes",
            min=0.0,
            help="Maximum time to wait for network after wake.",
        ),
    ] = 10.0,
) -> None:
    """Install the user LaunchAgent for wake-triggered autorun."""

    healthy_executable = shutil.which("healthy")
    if healthy_executable is None:
        console.print("[red]Could not find healthy on PATH.[/red] Run ./install.sh first.")
        raise typer.Exit(1)

    path = install_launch_agent(
        healthy_executable=healthy_executable,
        sync_interval_minutes=sync_interval_minutes,
        network_timeout_minutes=network_timeout_minutes,
    )
    console.print(f"[green]Installed autorun LaunchAgent:[/green] {path}")


@autorun_app.command("uninstall")
def uninstall_autorun() -> None:
    """Uninstall the user LaunchAgent for wake-triggered autorun."""

    path = uninstall_launch_agent()
    console.print(f"[green]Uninstalled autorun LaunchAgent:[/green] {path}")


@autorun_app.command("status")
def autorun_status() -> None:
    """Show autorun installation status and last successful sync."""

    if launch_agent_installed():
        console.print("[green]Autorun LaunchAgent is installed.[/green]")
    else:
        console.print("[yellow]Autorun LaunchAgent is not installed.[/yellow]")

    last_sync = AutorunStateStore(DEFAULT_AUTORUN_STATE).read_last_sync()
    if last_sync is None:
        console.print("Last successful sync: [yellow]never[/yellow]")
    else:
        age_minutes = round((datetime.now(UTC) - last_sync).total_seconds() / 60)
        local_time = last_sync.astimezone().strftime("%Y-%m-%d %H:%M")
        console.print(f"Last successful sync: {local_time} ({age_minutes} minutes ago)")

    wake_state = "full wake" if is_fully_awake() else "dark wake"
    console.print(f"Current power state: {wake_state}")


@autorun_app.command("tick", hidden=True)
def autorun_tick(
    sync_interval_minutes: Annotated[
        float,
        typer.Option("--sync-interval-minutes", "--sleep-threshold-minutes", min=1.0),
    ] = 30.0,
    network_timeout_minutes: Annotated[
        float,
        typer.Option("--network-timeout-minutes", min=0.0),
    ] = 10.0,
    output_dir: Annotated[
        Path,
        typer.Option("--output-dir", help="Local activity storage directory."),
    ] = DEFAULT_ACTIVITY_DIR,
    download_format: Annotated[
        DownloadFormat,
        typer.Option("--format", case_sensitive=False, help="Activity download format."),
    ] = DownloadFormat.ORIGINAL,
    storage_compression: Annotated[
        StorageCompression,
        typer.Option("--storage-compression", case_sensitive=False, help="Compress stored activity files."),
    ] = StorageCompression.NONE,
    tokenstore: Annotated[
        Path,
        typer.Option("--tokenstore", help="Directory containing garminconnect auth tokens."),
    ] = DEFAULT_TOKENSTORE,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Log what would happen without showing a notification or downloading."),
    ] = False,
) -> None:
    """Run one autorun tick. Intended for launchd."""

    logger = append_log(DEFAULT_AUTORUN_LOG)
    state_store = AutorunStateStore(DEFAULT_AUTORUN_STATE)
    result = evaluate_autorun_tick(
        state_store=state_store,
        config=AutorunConfig(
            sync_interval_minutes=sync_interval_minutes,
            network_timeout_minutes=network_timeout_minutes,
        ),
        log=logger,
        is_awake=is_fully_awake,
    )
    if dry_run:
        console.print(result.message)
    if result.decision is AutorunDecision.NETWORK_UNAVAILABLE:
        logger("autorun aborted; network not ready")
        if not dry_run:
            show_macos_notification("healthy", "Network was not ready after wake.", "Auto-run failed")
        raise typer.Exit(1)
    if not result.should_download:
        return
    if dry_run:
        console.print("download skipped by --dry-run")
        return

    summary = _download_for_autorun(
        output_dir=output_dir,
        download_format=download_format,
        storage_compression=storage_compression,
        tokenstore=tokenstore,
        log=logger,
    )
    state_store.write_last_sync(datetime.now(UTC))
    title, message = _autorun_download_notification(summary)
    show_macos_notification("healthy", _with_human_timestamp(message), title)
    logger(f"autorun download result: {message}")
    if summary.failed or summary.rate_limited:
        raise typer.Exit(1)


def _download_for_autorun(
    *,
    output_dir: Path,
    download_format: DownloadFormat,
    storage_compression: StorageCompression,
    tokenstore: Path,
    log: Callable[[str], None],
) -> DownloadSummary:
    """Download inside a power assertion so a re-sleep cannot kill the sync."""

    try:
        with power_assertion():
            return _run_background_download(
                output_dir=output_dir,
                download_format=download_format,
                storage_compression=storage_compression,
                tokenstore=tokenstore,
                log=log,
            )
    except BackgroundAuthError as exc:
        log(f"autorun auth failed: {exc}")
        show_macos_notification(
            "healthy",
            "Garmin auth expired — run healthy auth login",
            "Auto-run failed",
        )
        raise typer.Exit(1) from exc
    except Exception as exc:
        log(f"autorun failed: {exc}")
        show_macos_notification(
            "healthy",
            "healthy auto-run failed — see log",
            "Auto-run failed",
        )
        raise typer.Exit(1) from exc


class BackgroundAuthError(RuntimeError):
    """Raised when background Garmin authentication cannot continue."""


def _run_background_download(
    *,
    output_dir: Path,
    download_format: DownloadFormat,
    storage_compression: StorageCompression,
    tokenstore: Path,
    log: Callable[[str], None],
) -> DownloadSummary:
    try:
        garmin = GarminConnectActivityClient.login(
            tokenstore=tokenstore,
            email=None,
            password=None,
            prompt_mfa=lambda: _raise_background_auth_required(),
            rate_limit_policy=RateLimitPolicy(),
            on_rate_limit_retry=lambda delay, attempt, max_retries, exc: log(
                f"rate limit retry {attempt}/{max_retries} in {delay:.0f}s: {exc}"
            ),
        )
    except Exception as exc:
        raise BackgroundAuthError(str(exc)) from exc
    storage = FileActivityStorage(output_dir, compression=storage_compression)
    use_case = DownloadActivitiesUseCase(
        garmin,
        storage,
        on_progress=lambda event, activity: log(
            f"activity {event}: {activity.start_time_local} {activity.id} {activity.name}"
        ),
    )
    return use_case.execute(download_format=download_format)


def _raise_background_auth_required() -> str:
    raise BackgroundAuthError("background autorun cannot prompt for Garmin MFA")


def _with_human_timestamp(message: str) -> str:
    return f"{message} at {datetime.now().strftime('%Y-%m-%d %H:%M')}"


def _autorun_download_notification(summary: DownloadSummary) -> tuple[str, str]:
    if summary.rate_limited or summary.failed:
        return "Auto-run failed", "healthy auto-run failed — see log"
    if summary.downloaded:
        noun = "activity" if summary.downloaded == 1 else "activities"
        return "Auto-run complete", f"Downloaded {summary.downloaded} new {noun}"
    return "Auto-run complete", "No new Garmin activity"


def _print_activity_event(event: str, activity: Activity) -> None:
    label = {
        "exists": "[yellow]exists[/yellow]",
        "download": "[cyan]download[/cyan]",
        "saved": "[green]saved[/green]",
        "failed": "[red]failed[/red]",
        "rate_limited": "[red]rate limited[/red]",
    }.get(event, event)
    console.print(f"{label} {activity.start_time_local} {activity.id} {activity.name}")


def _print_rate_limit_retry(delay: float, attempt: int, max_retries: int, exc: BaseException) -> None:
    console.print(
        "[yellow]Garmin rate limit hit[/yellow]; "
        f"retry {attempt}/{max_retries} in {delay:.0f}s ({exc})"
    )


def _print_summary(summary: DownloadSummary, output_dir: Path) -> None:
    table = Table(title="Garmin activity download summary")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    table.add_row("Inspected", str(summary.inspected))
    table.add_row("Downloaded", str(summary.downloaded))
    table.add_row("Already local", str(summary.skipped_existing))
    table.add_row("Failed", str(summary.failed))
    table.add_row("Rate limited", "yes" if summary.rate_limited else "no")
    table.add_row("Stopped at first local activity", "yes" if summary.stopped_at_existing else "no")
    table.add_row("Storage", str(output_dir))
    console.print(table)

    if summary.saved_paths:
        console.print("[bold]Saved files:[/bold]")
        for path in summary.saved_paths:
            console.print(f"  {path}")
