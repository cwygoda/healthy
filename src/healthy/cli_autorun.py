"""Command line adapter for wake-triggered autoruns."""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Callable

import typer

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
from healthy.cli_common import (
    DEFAULT_ACTIVITY_DIR,
    DEFAULT_AUTORUN_LOG,
    DEFAULT_AUTORUN_STATE,
    DEFAULT_STORAGE_COMPRESSION,
    DEFAULT_TOKENSTORE,
    console,
)
from healthy.domain import DownloadFormat, DownloadSummary

autorun_app = typer.Typer(help="Run healthy automatically after wake.", no_args_is_help=True)


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
    ] = DEFAULT_STORAGE_COMPRESSION,
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
