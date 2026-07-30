import base64
import json
import mimetypes
import os
import queue
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable, Protocol, Sequence, TextIO, cast

from trading_agent.providers.base import ProviderUnavailable


class AcpCompletionClient(Protocol):
    def complete(
        self,
        prompt: str,
        *,
        image_paths: Sequence[Path] = (),
    ) -> str:
        ...


class _Process(Protocol):
    stdin: TextIO | None
    stdout: TextIO | None
    stderr: TextIO | None
    returncode: int | None

    def poll(self) -> int | None:
        ...

    def wait(self, timeout: float | None = None) -> int:
        ...

    def terminate(self) -> None:
        ...

    def kill(self) -> None:
        ...


ProcessFactory = Callable[..., _Process]


def _start_process(command: list[str], **kwargs: Any) -> _Process:
    return cast(_Process, subprocess.Popen(command, **kwargs))


def _safe_environment(temp_root: Path) -> dict[str, str]:
    environment = {
        key: value
        for key, value in os.environ.items()
        if key in {"PATH", "HOME", "LANG", "LC_ALL"}
    }
    environment["TMPDIR"] = str(temp_root)
    return environment


def _mime_type(path: Path) -> str:
    guessed, _ = mimetypes.guess_type(path.name)
    if guessed in {"image/png", "image/jpeg", "image/webp", "image/gif"}:
        return guessed
    raise ProviderUnavailable(f"kimi ACP does not support image type: {path.suffix}")


def _content_blocks(
    prompt: str,
    image_paths: Sequence[Path],
) -> list[dict[str, str]]:
    blocks: list[dict[str, str]] = [{"type": "text", "text": prompt}]
    for path in image_paths:
        try:
            data = base64.b64encode(path.read_bytes()).decode("ascii")
        except OSError as exc:
            raise ProviderUnavailable(f"kimi ACP cannot read image: {exc}") from exc
        blocks.append(
            {
                "type": "image",
                "data": data,
                "mimeType": _mime_type(path),
            }
        )
    return blocks


class KimiAcpClient:
    def __init__(
        self,
        *,
        model: str,
        timeout_seconds: float = 120.0,
        process_factory: ProcessFactory = _start_process,
    ) -> None:
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.process_factory = process_factory

    def complete(
        self,
        prompt: str,
        *,
        image_paths: Sequence[Path] = (),
    ) -> str:
        deadline = time.monotonic() + self.timeout_seconds
        with tempfile.TemporaryDirectory(prefix="trading-agent-kimi-acp-") as temp_dir:
            isolated_root = Path(temp_dir)
            empty_skills = isolated_root / "skills"
            empty_skills.mkdir()
            process = self._create_process(isolated_root, empty_skills)

            messages: queue.Queue[dict[str, Any] | BaseException | None] = queue.Queue()
            reader = threading.Thread(
                target=self._read_messages,
                args=(process, messages),
                daemon=True,
            )
            reader.start()
            chunks: list[str] = []
            try:
                initialize = self._request(
                    process,
                    messages,
                    deadline,
                    request_id=1,
                    method="initialize",
                    params=self._initialize_params(),
                    chunks=chunks,
                )
                if image_paths and not self._supports_images(initialize):
                    raise ProviderUnavailable(
                        "kimi ACP agent does not advertise image input"
                    )

                session = self._request(
                    process,
                    messages,
                    deadline,
                    request_id=2,
                    method="session/new",
                    params={
                        "cwd": str(isolated_root),
                        "mcpServers": [],
                    },
                    chunks=chunks,
                )
                session_id = session.get("sessionId")
                if not isinstance(session_id, str) or not session_id:
                    raise ProviderUnavailable("kimi ACP returned no session id")

                result = self._request(
                    process,
                    messages,
                    deadline,
                    request_id=3,
                    method="session/prompt",
                    params={
                        "sessionId": session_id,
                        "prompt": _content_blocks(prompt, image_paths),
                    },
                    chunks=chunks,
                )
                stop_reason = result.get("stopReason")
                if stop_reason != "end_turn":
                    raise ProviderUnavailable(
                        f"kimi ACP stopped without a completed turn: {stop_reason}"
                    )
                output = "".join(chunks).strip()
                if not output:
                    raise ProviderUnavailable("kimi ACP returned empty output")
                return output
            finally:
                self._stop_process(process)

    def probe(self, *, require_image: bool = True) -> None:
        deadline = time.monotonic() + self.timeout_seconds
        with tempfile.TemporaryDirectory(prefix="trading-agent-kimi-acp-") as temp_dir:
            isolated_root = Path(temp_dir)
            empty_skills = isolated_root / "skills"
            empty_skills.mkdir()
            process = self._create_process(isolated_root, empty_skills)
            messages: queue.Queue[dict[str, Any] | BaseException | None] = queue.Queue()
            reader = threading.Thread(
                target=self._read_messages,
                args=(process, messages),
                daemon=True,
            )
            reader.start()
            try:
                initialize = self._request(
                    process,
                    messages,
                    deadline,
                    request_id=1,
                    method="initialize",
                    params=self._initialize_params(),
                    chunks=[],
                )
                if require_image and not self._supports_images(initialize):
                    raise ProviderUnavailable(
                        "kimi ACP agent does not advertise image input"
                    )
                session = self._request(
                    process,
                    messages,
                    deadline,
                    request_id=2,
                    method="session/new",
                    params={"cwd": str(isolated_root), "mcpServers": []},
                    chunks=[],
                )
                if not isinstance(session.get("sessionId"), str):
                    raise ProviderUnavailable("kimi ACP returned no session id")
            finally:
                self._stop_process(process)

    def _create_process(self, isolated_root: Path, empty_skills: Path) -> _Process:
        command = [
            "kimi",
            "-m",
            self.model,
            "--skills-dir",
            str(empty_skills),
            "acp",
        ]
        try:
            return self.process_factory(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1,
                cwd=isolated_root,
                env=_safe_environment(isolated_root),
            )
        except OSError as exc:
            raise ProviderUnavailable(f"kimi ACP unavailable: {exc}") from exc

    @staticmethod
    def _initialize_params() -> dict[str, Any]:
        return {
            "protocolVersion": 1,
            "clientCapabilities": {
                "fs": {
                    "readTextFile": False,
                    "writeTextFile": False,
                },
                "terminal": False,
            },
            "clientInfo": {
                "name": "panshi-trading-ai",
                "title": "Panshi Trading AI",
                "version": "0.1.0",
            },
        }

    @staticmethod
    def _supports_images(initialize: dict[str, Any]) -> bool:
        return bool(
            initialize.get("agentCapabilities", {})
            .get("promptCapabilities", {})
            .get("image", False)
        )

    @staticmethod
    def _read_messages(
        process: _Process,
        messages: queue.Queue[dict[str, Any] | BaseException | None],
    ) -> None:
        if process.stdout is None:
            messages.put(ProviderUnavailable("kimi ACP stdout is unavailable"))
            return
        try:
            while True:
                line = process.stdout.readline()
                if not line:
                    messages.put(None)
                    return
                try:
                    decoded = json.loads(line)
                except json.JSONDecodeError as exc:
                    messages.put(
                        ProviderUnavailable(f"kimi ACP returned invalid JSON-RPC: {exc}")
                    )
                    return
                if not isinstance(decoded, dict):
                    messages.put(
                        ProviderUnavailable("kimi ACP returned a non-object message")
                    )
                    return
                messages.put(decoded)
        except BaseException as exc:
            messages.put(exc)

    def _request(
        self,
        process: _Process,
        messages: queue.Queue[dict[str, Any] | BaseException | None],
        deadline: float,
        *,
        request_id: int,
        method: str,
        params: dict[str, Any],
        chunks: list[str],
    ) -> dict[str, Any]:
        self._send(
            process,
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
                "params": params,
            },
        )
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ProviderUnavailable("kimi ACP timed out")
            try:
                message = messages.get(timeout=remaining)
            except queue.Empty as exc:
                raise ProviderUnavailable("kimi ACP timed out") from exc
            if message is None:
                raise ProviderUnavailable("kimi ACP closed before completing the request")
            if isinstance(message, BaseException):
                if isinstance(message, ProviderUnavailable):
                    raise message
                raise ProviderUnavailable(f"kimi ACP reader failed: {message}") from message
            if "method" in message and "id" in message:
                self._handle_agent_request(process, message)
                continue
            if message.get("method") == "session/update":
                self._capture_chunk(message, chunks)
                continue
            if message.get("id") != request_id:
                continue
            error = message.get("error")
            if error is not None:
                raise ProviderUnavailable(f"kimi ACP {method} failed: {error}")
            result = message.get("result")
            if not isinstance(result, dict):
                raise ProviderUnavailable(f"kimi ACP {method} returned invalid result")
            return result

    @staticmethod
    def _capture_chunk(message: dict[str, Any], chunks: list[str]) -> None:
        update = message.get("params", {}).get("update", {})
        if update.get("sessionUpdate") != "agent_message_chunk":
            return
        content = update.get("content", {})
        text = content.get("text")
        if content.get("type") == "text" and isinstance(text, str):
            chunks.append(text)

    def _handle_agent_request(
        self,
        process: _Process,
        message: dict[str, Any],
    ) -> None:
        request_id = message["id"]
        if message.get("method") != "session/request_permission":
            self._send(
                process,
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {
                        "code": -32601,
                        "message": "Client method is not supported",
                    },
                },
            )
            return
        options = message.get("params", {}).get("options", [])
        rejected = next(
            (
                option
                for option in options
                if isinstance(option, dict)
                and str(option.get("kind", "")).startswith("reject")
                and isinstance(option.get("optionId"), str)
            ),
            None,
        )
        outcome: dict[str, str]
        if rejected is None:
            outcome = {"outcome": "cancelled"}
        else:
            outcome = {
                "outcome": "selected",
                "optionId": rejected["optionId"],
            }
        self._send(
            process,
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {"outcome": outcome},
            },
        )

    @staticmethod
    def _send(process: _Process, message: dict[str, Any]) -> None:
        if process.stdin is None:
            raise ProviderUnavailable("kimi ACP stdin is unavailable")
        try:
            process.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
            process.stdin.flush()
        except OSError as exc:
            raise ProviderUnavailable(f"kimi ACP write failed: {exc}") from exc

    @staticmethod
    def _stop_process(process: _Process) -> None:
        if process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=2)
        except (subprocess.TimeoutExpired, TimeoutError):
            process.kill()
            try:
                process.wait(timeout=2)
            except (subprocess.TimeoutExpired, TimeoutError):
                pass
