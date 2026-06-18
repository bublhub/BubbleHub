from __future__ import annotations

import os
import shutil
import socket
import subprocess
import tempfile
import time
from contextlib import closing
from pathlib import Path

import requests

from ageos.engine.registry import ModelSpec


class LlamaBackend:
    def __init__(self) -> None:
        self.process: subprocess.Popen[str] | None = None
        self.port: int | None = None
        self.log_path: Path | None = None
        self.log_handle = None
        self.attached_pid: int = 0

    @property
    def pid(self) -> int:
        return int(self.process.pid) if self.process is not None else self.attached_pid

    def start(self, model: ModelSpec, model_path: str, niceness: int = 0) -> None:
        binary = shutil.which("llama-server")
        if binary is None:
            raise RuntimeError(
                "llama-server not found on PATH. Install llama.cpp or run scripts/install-deps.sh"
            )
        self.port = _free_port()
        args = [
            binary,
            "--model",
            model_path,
            "--host",
            "127.0.0.1",
            "--port",
            str(self.port),
            "--ctx-size",
            str(_llama_ctx_size()),
            "--parallel",
            str(_llama_parallel()),
        ]
        self.log_handle = tempfile.NamedTemporaryFile(
            mode="w+",
            encoding="utf-8",
            prefix="ageos-llama-",
            suffix=".log",
            delete=False,
        )
        self.log_path = Path(self.log_handle.name)
        self.process = subprocess.Popen(
            args,
            env=_llama_env(binary),
            text=True,
            stdout=self.log_handle,
            stderr=subprocess.STDOUT,
        )
        try:
            _wait_for_http(f"http://127.0.0.1:{self.port}/health", self.process, self.log_path)
        except Exception:
            self.stop()
            raise

    def attach(self, port: int, pid: int | None = None) -> None:
        self.port = int(port)
        self.attached_pid = int(pid or 0)
        _wait_for_attached_http(f"http://127.0.0.1:{self.port}/health", pid)

    def chat(self, messages: list[dict[str, str]], stream: bool = False, max_tokens: int | None = None) -> str:
        if self.port is None:
            raise RuntimeError("llama backend is not running")
        payload: dict[str, object] = {"model": "local", "messages": messages, "stream": False}
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        response = requests.post(
            f"http://127.0.0.1:{self.port}/v1/chat/completions",
            json=payload,
            timeout=300,
        )
        if response.status_code >= 400:
            raise RuntimeError(
                f"llama chat request failed with HTTP {response.status_code}: {response.text[:1000]}"
            )
        data = response.json()
        return data["choices"][0]["message"]["content"]

    def embeddings(self, inputs: list[str]) -> list[list[float]]:
        if self.port is None:
            raise RuntimeError("llama backend is not running")
        response = requests.post(
            f"http://127.0.0.1:{self.port}/v1/embeddings",
            json={"model": "local", "input": inputs},
            timeout=300,
        )
        if response.status_code >= 400:
            raise requests.HTTPError(
                f"llama embeddings request failed with HTTP {response.status_code}: {response.text[:1000]}",
                response=response,
            )
        data = response.json()
        return [item["embedding"] for item in data["data"]]

    def stop(self) -> None:
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
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
        self.log_path = None
        self.log_handle = None
        self.attached_pid = 0


def _free_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _llama_ctx_size() -> int:
    value = os.environ.get("AGEOS_LLAMA_CTX_SIZE", "32768")
    try:
        ctx_size = int(value)
    except ValueError:
        raise RuntimeError("AGEOS_LLAMA_CTX_SIZE must be an integer") from None
    if ctx_size <= 0:
        raise RuntimeError("AGEOS_LLAMA_CTX_SIZE must be greater than zero")
    return ctx_size


def _llama_parallel() -> int:
    value = os.environ.get("AGEOS_LLAMA_PARALLEL", "1")
    try:
        parallel = int(value)
    except ValueError:
        raise RuntimeError("AGEOS_LLAMA_PARALLEL must be an integer") from None
    if parallel <= 0:
        raise RuntimeError("AGEOS_LLAMA_PARALLEL must be greater than zero")
    return parallel


def _llama_env(binary: str) -> dict[str, str]:
    env = os.environ.copy()
    env["LD_LIBRARY_PATH"] = os.pathsep.join(_trusted_library_dirs(binary))
    return env


def _trusted_library_dirs(binary: str) -> list[str]:
    binary_path = Path(binary).resolve()
    candidates = [
        binary_path.parent,
        binary_path.parent.parent / "lib",
        binary_path.parent.parent / "lib64",
        Path("/usr/local/lib/x86_64-linux-gnu"),
        Path("/usr/local/lib"),
        Path("/usr/lib/x86_64-linux-gnu"),
        Path("/usr/lib"),
    ]
    dirs: list[str] = []
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if resolved.is_dir() and str(resolved) not in dirs:
            dirs.append(str(resolved))
    return dirs


def _wait_for_http(
    url: str,
    process: subprocess.Popen[str],
    log_path: Path,
    timeout_seconds: int = 120,
) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        return_code = process.poll()
        if return_code is not None:
            raise RuntimeError(
                f"llama backend exited before becoming healthy (exit code {return_code}).\n"
                f"{_read_log_tail(log_path)}"
            )
        try:
            if requests.get(url, timeout=1).status_code < 500:
                return
        except requests.RequestException:
            time.sleep(0.5)
    raise RuntimeError(f"llama backend did not become healthy: {url}\n{_read_log_tail(log_path)}")


def _wait_for_attached_http(url: str, pid: int | None, timeout_seconds: int = 5) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if pid and not _pid_exists(pid):
            raise RuntimeError(f"warm llama backend process {pid} is no longer running")
        try:
            if requests.get(url, timeout=1).status_code < 500:
                return
        except requests.RequestException:
            time.sleep(0.25)
    raise RuntimeError(f"warm llama backend is not healthy: {url}")


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
        return "No llama backend startup logs were captured."
    return f"llama backend startup log tail:\n{content}"
