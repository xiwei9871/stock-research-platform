#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fcntl
import os
import signal
import subprocess
import sys
from pathlib import Path


LOCKED_EXIT_CODE = 75


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lock-file", required=True)
    parser.add_argument("--guard-env", default="")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.command[:1] == ["--"]:
        args.command = args.command[1:]
    if not args.command:
        parser.error("a command is required after --")
    return args


def main() -> int:
    args = _parse_args()
    lock_path = Path(args.lock_file)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return LOCKED_EXIT_CODE

        os.set_inheritable(lock_fd, True)
        environment = os.environ.copy()
        if args.guard_env:
            environment[args.guard_env] = "1"
        child = subprocess.Popen(
            args.command,
            env=environment,
            start_new_session=True,
            pass_fds=(lock_fd,),
        )

        def forward(signum: int, _frame: object) -> None:
            try:
                os.killpg(child.pid, signum)
            except ProcessLookupError:
                pass

        for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
            signal.signal(signum, forward)

        return_code = child.wait()
        return return_code if return_code >= 0 else 128 - return_code
    finally:
        os.close(lock_fd)


if __name__ == "__main__":
    sys.exit(main())
