from stock_research.feishu_notify import send_openclaw_feishu_message


def test_send_openclaw_feishu_message_invokes_openclaw(monkeypatch):
    calls = []
    monkeypatch.setattr("subprocess.run", lambda cmd, check: calls.append((cmd, check)))

    send_openclaw_feishu_message(
        message="report",
        target="oc_group",
        account="jarvis",
        openclaw_bin="openclaw",
    )

    assert calls == [
        (
            [
                "openclaw",
                "message",
                "send",
                "--channel",
                "feishu",
                "--account",
                "jarvis",
                "--target",
                "oc_group",
                "--message",
                "report",
            ],
            True,
        )
    ]


def test_send_openclaw_feishu_message_supports_dry_run(monkeypatch):
    calls = []
    monkeypatch.setattr("subprocess.run", lambda cmd, check: calls.append((cmd, check)))

    send_openclaw_feishu_message(
        message="report",
        target="oc_group",
        dry_run=True,
    )

    assert calls[0][0][-1] == "--dry-run"
