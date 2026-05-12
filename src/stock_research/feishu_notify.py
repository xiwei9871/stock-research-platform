import subprocess


def send_openclaw_feishu_message(
    *,
    message: str,
    target: str,
    account: str = "jarvis",
    openclaw_bin: str = "openclaw",
    dry_run: bool = False,
) -> None:
    cmd = [
        openclaw_bin,
        "message",
        "send",
        "--channel",
        "feishu",
        "--account",
        account,
        "--target",
        target,
        "--message",
        message,
    ]
    if dry_run:
        cmd.append("--dry-run")
    subprocess.run(cmd, check=True)
