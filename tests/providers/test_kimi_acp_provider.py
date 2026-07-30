import base64
import io
import json
import subprocess
import time
from pathlib import Path

import pytest

from trading_agent.providers.base import ProviderUnavailable
from trading_agent.providers.kimi_acp import KimiAcpClient


FIXTURE = Path("tests/fixtures/charts/daily_boll_macd_volume.png")


class _CapturedStdin(io.StringIO):
    def close(self) -> None:
        pass


class _ScriptedProcess:
    def __init__(self, messages: list[dict[str, object]]) -> None:
        self.stdin = _CapturedStdin()
        self.stdout = io.StringIO(
            "".join(json.dumps(message) + "\n" for message in messages)
        )
        self.stderr = io.StringIO("")
        self.returncode: int | None = None
        self.terminated = False
        self.killed = False

    def poll(self) -> int | None:
        return self.returncode

    def wait(self, timeout: float | None = None) -> int:
        self.returncode = 0
        return 0

    def terminate(self) -> None:
        self.terminated = True
        self.returncode = 0

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9


class _BlockingStdout:
    def readline(self) -> str:
        time.sleep(0.2)
        return ""


class _BlockingProcess(_ScriptedProcess):
    def __init__(self) -> None:
        super().__init__([])
        self.stdout = _BlockingStdout()


def _messages(*, image: bool = True) -> list[dict[str, object]]:
    return [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "protocolVersion": 1,
                "agentCapabilities": {
                    "promptCapabilities": {"image": image},
                },
            },
        },
        {
            "jsonrpc": "2.0",
            "id": 2,
            "result": {"sessionId": "session-1"},
        },
        {
            "jsonrpc": "2.0",
            "id": 41,
            "method": "session/request_permission",
            "params": {
                "sessionId": "session-1",
                "toolCall": {"toolCallId": "tool-1"},
                "options": [
                    {
                        "optionId": "approve_once",
                        "name": "Approve once",
                        "kind": "allow_once",
                    },
                    {
                        "optionId": "reject",
                        "name": "Reject",
                        "kind": "reject_once",
                    },
                ],
            },
        },
        {
            "jsonrpc": "2.0",
            "method": "session/update",
            "params": {
                "sessionId": "session-1",
                "update": {
                    "sessionUpdate": "agent_message_chunk",
                    "content": {"type": "text", "text": '{"answer":'},
                },
            },
        },
        {
            "jsonrpc": "2.0",
            "method": "session/update",
            "params": {
                "sessionId": "session-1",
                "update": {
                    "sessionUpdate": "agent_message_chunk",
                    "content": {"type": "text", "text": '"ok"}'},
                },
            },
        },
        {
            "jsonrpc": "2.0",
            "id": 3,
            "result": {"stopReason": "end_turn"},
        },
    ]


def test_acp_sends_selected_model_original_image_and_denies_tools() -> None:
    captured: dict[str, object] = {}
    process = _ScriptedProcess(_messages())

    def process_factory(command, **kwargs):
        captured.update(command=command, kwargs=kwargs)
        return process

    output = KimiAcpClient(
        model="kimi-k3",
        process_factory=process_factory,
    ).complete("Return strict JSON.", image_paths=[FIXTURE])

    assert output == '{"answer":"ok"}'
    command = captured["command"]
    assert isinstance(command, list)
    assert command[:3] == ["kimi", "-m", "kimi-k3"]
    assert command[-1] == "acp"
    assert "--skills-dir" in command
    kwargs = captured["kwargs"]
    assert isinstance(kwargs, dict)
    assert kwargs["stderr"] is subprocess.DEVNULL

    requests = [
        json.loads(line)
        for line in process.stdin.getvalue().splitlines()
    ]
    assert [item.get("method") for item in requests[:3]] == [
        "initialize",
        "session/new",
        "session/prompt",
    ]
    initialize = requests[0]["params"]
    assert initialize["clientCapabilities"]["fs"] == {
        "readTextFile": False,
        "writeTextFile": False,
    }
    assert initialize["clientCapabilities"]["terminal"] is False

    blocks = requests[2]["params"]["prompt"]
    image = next(block for block in blocks if block["type"] == "image")
    assert image["mimeType"] == "image/png"
    assert base64.b64decode(image["data"]) == FIXTURE.read_bytes()
    assert not any(str(FIXTURE) in json.dumps(block) for block in blocks)

    permission_response = next(item for item in requests if item.get("id") == 41)
    assert permission_response["result"] == {
        "outcome": {"outcome": "selected", "optionId": "reject"}
    }
    assert process.terminated is True


def test_acp_fails_closed_when_agent_does_not_advertise_image_input() -> None:
    process = _ScriptedProcess(_messages(image=False))

    with pytest.raises(ProviderUnavailable, match="image"):
        KimiAcpClient(
            model="kimi-k3",
            process_factory=lambda *args, **kwargs: process,
        ).complete("Analyze.", image_paths=[FIXTURE])

    requests = [
        json.loads(line)
        for line in process.stdin.getvalue().splitlines()
    ]
    assert [item.get("method") for item in requests] == ["initialize"]
    assert process.terminated is True


def test_acp_probe_initializes_and_creates_session_without_prompt() -> None:
    process = _ScriptedProcess(_messages())

    KimiAcpClient(
        model="kimi-k3",
        process_factory=lambda *args, **kwargs: process,
    ).probe()

    requests = [
        json.loads(line)
        for line in process.stdin.getvalue().splitlines()
    ]
    assert [item.get("method") for item in requests] == [
        "initialize",
        "session/new",
    ]
    assert process.terminated is True


def test_acp_timeout_terminates_the_process() -> None:
    process = _BlockingProcess()

    with pytest.raises(ProviderUnavailable, match="timed out"):
        KimiAcpClient(
            model="kimi-k3",
            timeout_seconds=0.01,
            process_factory=lambda *args, **kwargs: process,
        ).complete("Analyze.")

    assert process.terminated is True


def test_acp_rejects_empty_agent_output() -> None:
    messages = _messages()
    messages = [
        message
        for message in messages
        if not (
            message.get("method") == "session/update"
            and message.get("params", {})
            .get("update", {})
            .get("sessionUpdate")
            == "agent_message_chunk"
        )
    ]
    process = _ScriptedProcess(messages)

    with pytest.raises(ProviderUnavailable, match="empty"):
        KimiAcpClient(
            model="kimi-k3",
            process_factory=lambda *args, **kwargs: process,
        ).complete("Analyze.")
