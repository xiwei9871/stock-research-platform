from pathlib import Path


def build_open_auction_minute_cron_entries(
    *,
    project_dir: str | Path,
    universe_path: str | Path,
    output_dir: str | Path = "outputs/research/open_auction_minute_collect",
    log_path: str | Path = "logs/open_auction_minute_collect.log",
    primary_hour: int = 9,
    primary_minute: int = 40,
    retry_hour: int = 15,
    retry_minute: int = 10,
) -> list[str]:
    project = Path(project_dir)
    env = (
        f"OPEN_AUCTION_MINUTE_UNIVERSE_PATH={universe_path} "
        f"OPEN_AUCTION_MINUTE_OUTPUT_DIR={output_dir}"
    )
    command = (
        f"cd {project} && {env} "
        'scripts/run_open_auction_minute_collect.sh "$(date +\\%F)" '
        f">> {log_path} 2>&1"
    )
    return [
        f"{primary_minute} {primary_hour} * * 1-5 {command}",
        f"{retry_minute} {retry_hour} * * 1-5 {command}",
    ]
