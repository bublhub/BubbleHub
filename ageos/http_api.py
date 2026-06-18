from __future__ import annotations

import json
import hashlib
import math
import os
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock
from typing import Any

import requests

from ageos.engine.registry import ModelRegistry
from ageos.engine.session import EngineSession


DEFAULT_MAX_OUTPUT_TOKENS = 512


@dataclass(frozen=True)
class ApiConfig:
    host: str = "127.0.0.1"
    port: int = 8000
    default_specialty: str = "default-instruct"
    niceness: int = 0
    status_callback: Callable[[str], None] | None = None


def run_http_api(config: ApiConfig) -> None:
    server = create_http_server(config)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return
    finally:
        server.server_close()


def create_http_server(config: ApiConfig) -> "AgeosHttpServer":
    return AgeosHttpServer((config.host, config.port), _handler_for(config), config)


class AgeosHttpServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        server_address: tuple[str, int],
        handler_class: type[BaseHTTPRequestHandler],
        config: ApiConfig,
    ) -> None:
        self.config = config
        self._session_lock = Lock()
        self._sessions: dict[str, tuple[EngineSession, EngineSession]] = {}
        super().__init__(server_address, handler_class)

    def preload(self, specialty: str | None = None) -> None:
        with self._session_lock:
            self._session_for(specialty or self.config.default_specialty)

    def chat(self, specialty: str, messages: list[dict[str, str]], max_tokens: int | None = None) -> str:
        with self._session_lock:
            try:
                return self._session_for(specialty).chat(messages, max_tokens=max_tokens)
            except Exception:
                self._drop_session(specialty, evict_model=True)
                return self._session_for(specialty).chat(messages, max_tokens=max_tokens)

    def embeddings(self, specialty: str, inputs: list[str]) -> list[list[float]]:
        with self._session_lock:
            try:
                return self._session_for(specialty).embeddings(inputs)
            except Exception:
                self._drop_session(specialty, evict_model=True)
                return self._session_for(specialty).embeddings(inputs)

    def server_close(self) -> None:
        with self._session_lock:
            sessions = list(self._sessions.values())
            self._sessions.clear()
        for manager, _session in sessions:
            manager.__exit__(None, None, None)
        super().server_close()

    def _session_for(self, specialty: str) -> EngineSession:
        cached = self._sessions.get(specialty)
        if cached is None:
            manager = EngineSession(
                specialty,
                niceness=self.config.niceness,
                status_callback=self.config.status_callback,
            )
            session = manager.__enter__()
            self._sessions[specialty] = (manager, session)
            return session
        _manager, session = cached
        return session

    def _drop_session(self, specialty: str, *, evict_model: bool = False) -> None:
        cached = self._sessions.pop(specialty, None)
        if cached is None:
            return
        manager, _session = cached
        model_name = None
        resolved = getattr(manager, "resolved", None)
        model = getattr(resolved, "model", None)
        if model is not None:
            model_name = getattr(model, "name", None)
        try:
            manager.__exit__(None, None, None)
        finally:
            if evict_model and model_name:
                try:
                    manager.scheduler.evict_model(str(model_name))
                except Exception:
                    pass


def chat_completion_payload(
    model: str,
    content: str,
    *,
    response_id: str | None = None,
    created: int | None = None,
) -> dict[str, Any]:
    return {
        "id": response_id or f"chatcmpl-{uuid.uuid4().hex}",
        "object": "chat.completion",
        "created": created or int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
    }


def responses_payload(
    model: str,
    content: str,
    *,
    response_id: str | None = None,
    created: int | None = None,
) -> dict[str, Any]:
    output_id = f"msg-{uuid.uuid4().hex}"
    text_id = f"txt-{uuid.uuid4().hex}"
    return {
        "id": response_id or f"resp-{uuid.uuid4().hex}",
        "object": "response",
        "created_at": created or int(time.time()),
        "status": "completed",
        "model": model,
        "output": [
            {
                "id": output_id,
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [
                    {
                        "id": text_id,
                        "type": "output_text",
                        "text": content,
                    }
                ],
            }
        ],
        "output_text": content,
    }


def embeddings_payload(model: str, vectors: list[list[float]], inputs: list[str] | None = None) -> dict[str, Any]:
    return {
        "object": "list",
        "model": model,
        "data": [
            {
                "object": "embedding",
                "index": index,
                "embedding": vector,
            }
            for index, vector in enumerate(vectors)
        ],
        "usage": {
            "prompt_tokens": sum(len(item.split()) for item in inputs or []),
            "total_tokens": sum(len(item.split()) for item in inputs or []),
        },
    }


def messages_from_responses_input(value: object) -> list[dict[str, str]]:
    if isinstance(value, str):
        return [{"role": "user", "content": value}]
    if isinstance(value, list):
        return normalize_chat_messages(value)
    raise ValueError("responses input must be a string or a list of messages")


def normalize_chat_messages(value: list[object]) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    system_parts: list[str] = []
    for item in value:
        if isinstance(item, str):
            content = item.strip()
            if content:
                messages.append({"role": "user", "content": content})
            continue
        if not isinstance(item, dict):
            continue
        role = _normalize_role(item.get("role"))
        content = _content_to_text(item.get("content", "")).strip()
        if not content and role == "assistant":
            continue
        if role == "assistant" and _is_failed_assistant_content(content):
            continue
        if not content:
            continue
        if str(item.get("role", "")).lower() in {"tool", "function"}:
            name = item.get("name") or item.get("tool_call_id") or "tool"
            content = f"Tool result ({name}):\n{content}"
        if role == "system":
            system_parts.append(content)
            continue
        messages.append({"role": role, "content": content})
    ordered = _normalize_message_order(messages, system_parts)
    if ordered:
        return ordered
    raise ValueError("messages must contain at least one text message")


def _normalize_message_order(
    messages: list[dict[str, str]],
    system_parts: list[str],
) -> list[dict[str, str]]:
    ordered: list[dict[str, str]] = []
    if system_parts:
        ordered.append({"role": "system", "content": "\n\n".join(system_parts)})
    for message in messages:
        role = message["role"]
        content = message["content"]
        if role == "assistant" and not any(item["role"] == "user" for item in ordered):
            continue
        if ordered and ordered[-1]["role"] == role:
            ordered[-1]["content"] = f"{ordered[-1]['content']}\n\n{content}"
            continue
        ordered.append({"role": role, "content": content})
    return ordered


def normalize_embeddings_input(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        if all(isinstance(item, str) for item in value):
            return [str(item) for item in value]
        if all(isinstance(item, int) for item in value):
            return [" ".join(str(item) for item in value)]
        if all(isinstance(item, list) for item in value):
            return [" ".join(str(token) for token in item) for item in value]
    raise ValueError("embeddings input must be a string, list of strings, or token list")


def _handler_for(config: ApiConfig) -> type[BaseHTTPRequestHandler]:
    class AgeosHttpHandler(BaseHTTPRequestHandler):
        server_version = "AgeOSHTTP/0.1"

        def do_GET(self) -> None:
            if self.path == "/health":
                self._send_json({"status": "ok"})
                return
            self._send_error(HTTPStatus.NOT_FOUND, f"unknown endpoint: {self.path}")

        def do_POST(self) -> None:
            try:
                body = self._read_json()
                if self.path == "/v1/chat/completions":
                    self._handle_chat_completions(body)
                elif self.path == "/v1/responses":
                    self._handle_responses(body)
                elif self.path == "/v1/embeddings":
                    self._handle_embeddings(body)
                else:
                    self._send_error(HTTPStatus.NOT_FOUND, f"unknown endpoint: {self.path}")
            except ValueError as exc:
                self._send_error(HTTPStatus.BAD_REQUEST, str(exc))
            except Exception as exc:  # noqa: BLE001 - convert backend failures to JSON API errors.
                self._send_error(HTTPStatus.BAD_GATEWAY, str(exc))

        def log_message(self, format: str, *args: object) -> None:
            return

        def _handle_chat_completions(self, body: dict[str, Any]) -> None:
            messages = body.get("messages")
            if not isinstance(messages, list) or not messages:
                raise ValueError("messages must be a non-empty list")
            normalized = normalize_chat_messages(messages)
            specialty = _specialty_from_body(body, config.default_specialty)
            max_tokens = _max_output_tokens(body, "max_tokens", "max_completion_tokens")
            content = _ageos_server(self.server).chat(specialty, normalized, max_tokens=max_tokens)
            model = _model_name(body, specialty)
            if body.get("stream"):
                self._send_chat_completion_stream(model, content)
            else:
                self._send_json(chat_completion_payload(model, content))

        def _handle_responses(self, body: dict[str, Any]) -> None:
            messages = messages_from_responses_input(body.get("input"))
            specialty = _specialty_from_body(body, config.default_specialty)
            max_tokens = _max_output_tokens(body, "max_output_tokens", "max_tokens")
            content = _ageos_server(self.server).chat(specialty, messages, max_tokens=max_tokens)
            model = _model_name(body, specialty)
            if body.get("stream"):
                self._send_responses_stream(model, content)
            else:
                self._send_json(responses_payload(model, content))

        def _handle_embeddings(self, body: dict[str, Any]) -> None:
            inputs = normalize_embeddings_input(body.get("input"))
            specialty = _specialty_from_body(body, config.default_specialty)
            dimensions = _embedding_dimensions(body)
            try:
                vectors = _ageos_server(self.server).embeddings(specialty, inputs)
            except requests.HTTPError as exc:
                status_code = exc.response.status_code if exc.response is not None else None
                if status_code not in {HTTPStatus.NOT_FOUND, HTTPStatus.NOT_IMPLEMENTED}:
                    raise
                vectors = fallback_embeddings(inputs, dimensions)
            self._send_json(embeddings_payload(_model_name(body, specialty), vectors, inputs))

        def _read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("content-length", "0"))
            if length <= 0:
                raise ValueError("request body is required")
            raw = self.rfile.read(length)
            data = json.loads(raw.decode("utf-8"))
            if not isinstance(data, dict):
                raise ValueError("request body must be a JSON object")
            return data

        def _send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
            encoded = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def _send_error(self, status: HTTPStatus, message: str) -> None:
            payload = {
                "error": {
                    "message": message,
                    "type": status.phrase.lower().replace(" ", "_"),
                    "code": status.value,
                }
            }
            self._send_json(payload, status=status)

        def _send_sse(self, events: list[dict[str, Any]]) -> None:
            self.send_response(HTTPStatus.OK)
            self.send_header("content-type", "text/event-stream")
            self.send_header("cache-control", "no-cache")
            self.send_header("connection", "close")
            self.end_headers()
            for event in events:
                self.wfile.write(f"data: {json.dumps(event)}\n\n".encode("utf-8"))
            self.wfile.write(b"data: [DONE]\n\n")

        def _send_chat_completion_stream(self, model: str, content: str) -> None:
            response_id = f"chatcmpl-{uuid.uuid4().hex}"
            created = int(time.time())
            self._send_sse(
                [
                    {
                        "id": response_id,
                        "object": "chat.completion.chunk",
                        "created": created,
                        "model": model,
                        "choices": [
                            {
                                "index": 0,
                                "delta": {"role": "assistant"},
                                "finish_reason": None,
                            }
                        ],
                    },
                    {
                        "id": response_id,
                        "object": "chat.completion.chunk",
                        "created": created,
                        "model": model,
                        "choices": [
                            {
                                "index": 0,
                                "delta": {"content": content},
                                "finish_reason": None,
                            }
                        ],
                    },
                    {
                        "id": response_id,
                        "object": "chat.completion.chunk",
                        "created": created,
                        "model": model,
                        "choices": [
                            {
                                "index": 0,
                                "delta": {},
                                "finish_reason": "stop",
                            }
                        ],
                    },
                ]
            )

        def _send_responses_stream(self, model: str, content: str) -> None:
            response = responses_payload(model, content)
            self._send_sse(
                [
                    {"type": "response.created", "response": {**response, "output": []}},
                    {
                        "type": "response.output_text.delta",
                        "item_id": response["output"][0]["id"],
                        "output_index": 0,
                        "content_index": 0,
                        "delta": content,
                    },
                    {"type": "response.completed", "response": response},
                ]
            )

    return AgeosHttpHandler


def _ageos_server(server: object) -> AgeosHttpServer:
    if not isinstance(server, AgeosHttpServer):
        raise RuntimeError("AgeOS HTTP handler is not attached to an AgeOS server")
    return server


def _content_to_text(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return str(value.get("text") or value.get("input_text") or value.get("output_text") or "")
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("input_text") or item.get("output_text") or ""))
            else:
                parts.append(str(item))
        return "\n".join(part for part in parts if part)
    return str(value)


def _normalize_role(value: object) -> str:
    role = str(value or "user").lower()
    if role == "developer":
        return "system"
    if role in {"system", "user", "assistant"}:
        return role
    return "user"


def _is_failed_assistant_content(content: str) -> bool:
    normalized = content.strip().lower()
    return normalized in {
        "[assistant turn failed before producing content]",
        "context overflow: prompt too large for the model. try /reset (or /new) to start a fresh session, or use a larger-context model.",
    }


def _specialty_from_body(body: dict[str, Any], default: str) -> str:
    explicit = body.get("ageos_specialty") or body.get("ageos_speciality")
    if explicit:
        return _resolve_specialty_alias(str(explicit), default)
    model = str(body.get("model", ""))
    return _resolve_specialty_alias(model, default)


def _model_name(body: dict[str, Any], specialty: str) -> str:
    model = body.get("model")
    return str(model) if model else specialty


def _max_output_tokens(body: dict[str, Any], *field_names: str) -> int:
    for field_name in field_names:
        value = body.get(field_name)
        if value is None:
            continue
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            raise ValueError(f"{field_name} must be an integer") from None
        if parsed > 0:
            return parsed
        break
    return _default_max_output_tokens()


def _default_max_output_tokens() -> int:
    value = os.environ.get("AGEOS_MAX_OUTPUT_TOKENS")
    if value is None:
        return DEFAULT_MAX_OUTPUT_TOKENS
    try:
        parsed = int(value)
    except ValueError:
        raise ValueError("AGEOS_MAX_OUTPUT_TOKENS must be an integer") from None
    if parsed <= 0:
        raise ValueError("AGEOS_MAX_OUTPUT_TOKENS must be greater than zero")
    return parsed


def _resolve_specialty_alias(value: str, default: str) -> str:
    registry = ModelRegistry.load_default()
    if value in registry.specialties:
        return value
    if value.startswith("openai/"):
        unprefixed = value.split("/", 1)[1]
        if unprefixed in registry.specialties:
            return unprefixed
    return default


def _embedding_dimensions(body: dict[str, Any]) -> int:
    value = body.get("dimensions", 384)
    try:
        dimensions = int(value)
    except (TypeError, ValueError):
        raise ValueError("dimensions must be an integer") from None
    if dimensions <= 0 or dimensions > 4096:
        raise ValueError("dimensions must be between 1 and 4096")
    return dimensions


def fallback_embeddings(inputs: list[str], dimensions: int = 384) -> list[list[float]]:
    """Return stable feature-hash embeddings when a backend has no embedding endpoint."""

    vectors: list[list[float]] = []
    for text in inputs:
        vector = [0.0] * dimensions
        tokens = text.lower().split() or [text.lower()]
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        vectors.append([value / norm for value in vector])
    return vectors
