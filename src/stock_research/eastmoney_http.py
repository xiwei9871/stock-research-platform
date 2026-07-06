import json
import os
import subprocess
from typing import Any
from urllib.parse import urlencode


EASTMONEY_CURL_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
PROXY_ENV_KEYS = {
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
}


def eastmoney_curl_env() -> dict[str, str]:
    return {key: value for key, value in os.environ.items() if key not in PROXY_ENV_KEYS}


def curl_eastmoney_json(
    urls: str | list[str],
    params: dict[str, Any],
    *,
    retries: int,
    retry_sleep_seconds: float,
    timeout_seconds: int = 15,
) -> dict[str, Any]:
    candidates = [urls] if isinstance(urls, str) else list(urls)
    errors: list[str] = []
    for url in candidates:
        query_url = f"{url}?{urlencode(params)}"
        command = [
            "curl",
            "-sS",
            "--fail",
            "--noproxy",
            "*",
            "--retry",
            str(max(0, retries - 1)),
            "--retry-all-errors",
            "--retry-delay",
            str(max(0, int(retry_sleep_seconds))),
            "--max-time",
            str(timeout_seconds),
            "-A",
            EASTMONEY_CURL_UA,
            query_url,
        ]
        result = subprocess.run(
            command,
            capture_output=True,
            env=eastmoney_curl_env(),
            text=True,
            timeout=timeout_seconds * max(1, retries) + 5,
        )
        if result.returncode != 0:
            errors.append(f"{url}: curl rc={result.returncode}: {result.stderr.strip()}")
            continue
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            errors.append(f"{url}: invalid JSON: {exc}")
    raise RuntimeError("Eastmoney curl failed: " + " | ".join(errors))
