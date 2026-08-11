"""Command line adapter for healthy."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.table import Table

from healthy.adapters.garmin import GarminConnectActivityClient
from healthy.adapters.rate_limit import RateLimitPolicy
from healthy.adapters.storage import FileActivityStorage, StorageCompression
from healthy.application import DownloadActivitiesUseCase
from healthy.cli_autorun import autorun_app
from healthy.cli_common import DEFAULT_ACTIVITY_DIR, DEFAULT_STORAGE_COMPRESSION, DEFAULT_TOKENSTORE, console
from healthy.domain import Activity, DownloadFormat, DownloadSummary

app = typer.Typer(
    help="Download Garmin Connect activities into local storage.",
    no_args_is_help=True,
)
auth_app = typer.Typer(help="Authenticate against Garmin Connect.", no_args_is_help=True)
activities_app = typer.Typer(help="Work with Garmin activities.", no_args_is_help=True)
app.add_typer(auth_app, name="auth")
app.add_typer(activities_app, name="activities")
app.add_typer(autorun_app, name="autorun")


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
    ] = DEFAULT_STORAGE_COMPRESSION,
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
