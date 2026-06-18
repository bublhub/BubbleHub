from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import time
from contextlib import closing
from importlib.util import find_spec
from pathlib import Path

import requests

from ageos.engine.registry import ModelSpec


class VllmBackend:
    def __init__(self) -> None:
        self.process: subprocess.Popen[str] | None = None
        self.port: int | None = None
        self.model_name: str | None = None
        self.log_path: Path | None = None
        self.log_handle = None
        self.attached_pid: int = 0

    @property
    def pid(self) -> int:
        return int(self.process.pid) if self.process is not None else self.attached_pid

    def start(self, model: ModelSpec, model_path: str, niceness: int = 0) -> None:
        if find_spec("vllm") is None:
            raise RuntimeError(
                "vLLM backend selected but vllm is not installed. "
                'Install it with: sudo /opt/ageos/bin/python -m pip install "ageos[vllm]"'
            )
        self.port = _free_port()
        self.model_name = model.name
        env = os.environ.copy()
        if "AGEOS_CUDA_VISIBLE_DEVICES" in env:
            env["CUDA_VISIBLE_DEVICES"] = env["AGEOS_CUDA_VISIBLE_DEVICES"]
        self.log_handle = tempfile.NamedTemporaryFile(
            mode="w+",
            encoding="utf-8",
            prefix="ageos-vllm-",
            suffix=".log",
            delete=False,
        )
        self.log_path = Path(self.log_handle.name)
        args = [
            sys.executable,
            "-m",
            "vllm.entrypoints.openai.api_server",
            "--model",
            model_path,
            "--served-model-name",
            model.name,
            "--host",
            "127.0.0.1",
            "--port",
            str(self.port),
        ]
        self.process = subprocess.Popen(
            args,
            env=env,
            text=True,
            stdout=self.log_handle,
            stderr=subprocess.STDOUT,
        )
        try:
            _wait_for_http(f"http://127.0.0.1:{self.port}/health", self.process, self.log_path)
        except Exception:
            self.stop()
            raise

    def attach(self, model: ModelSpec, port: int, pid: int | None = None) -> None:
        self.model_name = model.name
        self.port = int(port)
        self.attached_pid = int(pid or 0)
        _wait_for_attached_http(f"http://127.0.0.1:{self.port}/health", pid)

    def chat(self, messages: list[dict[str, str]], stream: bool = False, max_tokens: int | None = None) -> str:
        if self.port is None or self.model_name is None:
            raise RuntimeError("vLLM backend is not running")
        payload: dict[str, object] = {"model": self.model_name, "messages": messages, "stream": False}
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        response = requests.post(
            f"http://127.0.0.1:{self.port}/v1/chat/completions",
            json=payload,
            timeout=300,
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]

    def embeddings(self, inputs: list[str]) -> list[list[float]]:
        if self.port is None or self.model_name is None:
            raise RuntimeError("vLLM backend is not running")
        response = requests.post(
            f"http://127.0.0.1:{self.port}/v1/embeddings",
            json={"model": self.model_name, "input": inputs},
            timeout=300,
        )
        response.raise_for_status()
        data = response.json()
        return [item["embedding"] for item in data["data"]]

    def stop(self) -> None:
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
        if self.log_handle is not None:
            self.log_handle.close()
        if self.log_path is not None:
            try:
                self.log_path.unlink()
            except OSError:
                pass
        self.process = None
        self.port = None
        self.model_name = None
        self.log_path = None
        self.log_handle = None
        self.attached_pid = 0


def _free_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_http(
    url: str,
    process: subprocess.Popen[str],
    log_path: Path,
    timeout_seconds: int = 180,
) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        return_code = process.poll()
        if return_code is not None:
            raise RuntimeError(
                f"vLLM backend exited before becoming healthy (exit code {return_code}).\n"
                f"{_read_log_tail(log_path)}"
            )
        try:
            if requests.get(url, timeout=1).status_code < 500:
                return
        except requests.RequestException:
            time.sleep(0.5)
    raise RuntimeError(f"vLLM backend did not become healthy: {url}\n{_read_log_tail(log_path)}")


def _wait_for_attached_http(url: str, pid: int | None, timeout_seconds: int = 5) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if pid and not _pid_exists(pid):
            raise RuntimeError(f"warm vLLM backend process {pid} is no longer running")
        try:
            if requests.get(url, timeout=1).status_code < 500:
                return
        except requests.RequestException:
            time.sleep(0.25)
    raise RuntimeError(f"warm vLLM backend is not healthy: {url}")


def _pid_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _read_log_tail(path: Path, max_bytes: int = 4096) -> str:
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - max_bytes))
            content = handle.read().decode("utf-8", errors="replace").strip()
    except OSError:
        content = ""
    if not content:
        return "No vLLM startup logs were captured."
    return f"vLLM startup log tail:\n{content}"
