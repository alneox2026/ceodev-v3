from __future__ import annotations

import json
import logging
import os
import re
import threading
import uuid
from collections.abc import Iterator
from typing import Any

import firebase_admin
import functions_framework
import google.auth
from firebase_admin import auth as firebase_auth
from flask import Response
from google.auth.transport.requests import AuthorizedSession
from google.cloud import firestore
from requests import Response as RequestsResponse
from requests import exceptions as requests_exceptions
from requests.adapters import HTTPAdapter


logging.basicConfig(level=logging.INFO)
LOGGER = logging.getLogger(__name__)

DEFAULT_PROJECT_ID = "ceo-dev123"
DEFAULT_REGION = "us-central1"
DEFAULT_REASONING_ENGINE_ID = "6357932034928672768"
RESOURCE_NAME_PATTERN = re.compile(
    r"^projects/(?P<project_id>[^/]+)/locations/(?P<region>[^/]+)/reasoningEngines/(?P<engine_id>[^/]+)$"
)

GOOGLE_CLOUD_PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT", DEFAULT_PROJECT_ID)
RAW_AGENT_REGION = os.getenv("AGENT_REGION", "").strip()
FALLBACK_AGENT_REGION = RAW_AGENT_REGION or os.getenv(
    "GOOGLE_CLOUD_REGION",
    DEFAULT_REGION,
)
AGENT_RESOURCE_NAME = os.getenv(
    "AGENT_RESOURCE_NAME",
    (
        f"projects/{GOOGLE_CLOUD_PROJECT}/locations/{FALLBACK_AGENT_REGION}"
        f"/reasoningEngines/{DEFAULT_REASONING_ENGINE_ID}"
    ),
)
resource_match = RESOURCE_NAME_PATTERN.match(AGENT_RESOURCE_NAME.strip())
if not resource_match:
    raise RuntimeError(
        "AGENT_RESOURCE_NAME must match "
        "'projects/<project>/locations/<region>/reasoningEngines/<id>'."
    )

AGENT_PROJECT_ID = resource_match.group("project_id")
AGENT_REGION = resource_match.group("region")
AGENT_ENGINE_ID = resource_match.group("engine_id")

if RAW_AGENT_REGION and RAW_AGENT_REGION != AGENT_REGION:
    LOGGER.warning(
        "AGENT_REGION=%s does not match AGENT_RESOURCE_NAME region=%s. "
        "Using the region derived from AGENT_RESOURCE_NAME.",
        RAW_AGENT_REGION,
        AGENT_REGION,
    )

AGENT_QUERY_URL = os.getenv(
    "AGENT_QUERY_URL",
    f"https://{AGENT_REGION}-aiplatform.googleapis.com/v1/{AGENT_RESOURCE_NAME}:query",
)
AGENT_STREAM_QUERY_URL = os.getenv(
    "AGENT_STREAM_QUERY_URL",
    (
        f"https://{AGENT_REGION}-aiplatform.googleapis.com/v1/"
        f"{AGENT_RESOURCE_NAME}:streamQuery?alt=sse"
    ),
)
FIRESTORE_COLLECTION = os.getenv("FIRESTORE_COLLECTION", "ceoagent_sessions")
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*")
MIDDLEWARE_API_KEY = os.getenv("MIDDLEWARE_API_KEY", "").strip()
MAX_MESSAGE_CHARS = int(os.getenv("MAX_MESSAGE_CHARS", "20000"))
UPSTREAM_CONNECT_TIMEOUT_SECONDS = float(
    os.getenv("UPSTREAM_CONNECT_TIMEOUT_SECONDS", "10")
)
UPSTREAM_READ_TIMEOUT_SECONDS = float(os.getenv("UPSTREAM_READ_TIMEOUT_SECONDS", "55"))
UPSTREAM_POOL_MAXSIZE = int(os.getenv("UPSTREAM_POOL_MAXSIZE", "128"))
REQUIRE_FIREBASE_AUTH = (
    os.getenv("REQUIRE_FIREBASE_AUTH", "false").strip().lower() == "true"
)

AUTH_SCOPES = ("https://www.googleapis.com/auth/cloud-platform",)

_authorized_session: AuthorizedSession | None = None
_firestore_client: firestore.Client | None = None
_firebase_ready = False
_client_lock = threading.Lock()


class ApiError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}


def _parse_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    if isinstance(value, (int, float)):
        return bool(value)
    return default


def _allowed_origins() -> set[str] | None:
    if ALLOWED_ORIGINS.strip() == "*":
        return None
    return {
        origin.strip()
        for origin in ALLOWED_ORIGINS.split(",")
        if origin.strip()
    }


def _build_cors_headers(origin: str | None) -> dict[str, str]:
    headers = {
        "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
        "Access-Control-Allow-Headers": "Authorization,Content-Type,X-Api-Key",
        "Access-Control-Max-Age": "3600",
    }
    allowed = _allowed_origins()
    if allowed is None:
        headers["Access-Control-Allow-Origin"] = "*"
    elif origin and origin in allowed:
        headers["Access-Control-Allow-Origin"] = origin
        headers["Vary"] = "Origin"
    return headers


def _check_origin(origin: str | None) -> None:
    allowed = _allowed_origins()
    if allowed is None or not origin:
        return
    if origin not in allowed:
        raise ApiError(
            403,
            "origin_not_allowed",
            "The request origin is not allowed by this middleware.",
            {"origin": origin},
        )


def _json_response(
    payload: dict[str, Any],
    status_code: int,
    origin: str | None,
) -> tuple[str, int, dict[str, str]]:
    headers = _build_cors_headers(origin)
    headers["Content-Type"] = "application/json"
    return json.dumps(payload, default=str), status_code, headers


def _error_response(error: ApiError, origin: str | None) -> tuple[str, int, dict[str, str]]:
    LOGGER.warning(
        json.dumps(
            {
                "severity": "WARNING",
                "event": "middleware_error",
                "code": error.code,
                "status_code": error.status_code,
                "details": error.details,
            }
        )
    )
    return _json_response(
        {
            "ok": False,
            "error": {
                "code": error.code,
                "message": error.message,
                "details": error.details,
            },
        },
        error.status_code,
        origin,
    )


def _get_authorized_session() -> AuthorizedSession:
    global _authorized_session
    if _authorized_session is None:
        with _client_lock:
            if _authorized_session is None:
                credentials, _ = google.auth.default(scopes=AUTH_SCOPES)
                _authorized_session = AuthorizedSession(credentials)
                adapter = HTTPAdapter(
                    pool_connections=UPSTREAM_POOL_MAXSIZE,
                    pool_maxsize=UPSTREAM_POOL_MAXSIZE,
                    max_retries=0,
                    pool_block=False,
                )
                _authorized_session.mount("https://", adapter)
                _authorized_session.mount("http://", adapter)
    return _authorized_session


def _get_firestore_client() -> firestore.Client:
    global _firestore_client
    if _firestore_client is None:
        with _client_lock:
            if _firestore_client is None:
                _firestore_client = firestore.Client(project=GOOGLE_CLOUD_PROJECT)
    return _firestore_client


def _ensure_firebase_initialized() -> None:
    global _firebase_ready
    if _firebase_ready:
        return
    with _client_lock:
        if _firebase_ready:
            return
        firebase_admin.initialize_app()
        _firebase_ready = True


def _extract_bearer_token(authorization_header: str | None) -> str | None:
    if not authorization_header:
        return None
    scheme, _, token = authorization_header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise ApiError(
            401,
            "invalid_authorization_header",
            "Authorization must be a Bearer token.",
        )
    return token.strip()


def _authenticate_request(request, payload: dict[str, Any]) -> str:
    if MIDDLEWARE_API_KEY:
        supplied_api_key = request.headers.get("X-Api-Key", "").strip()
        if supplied_api_key != MIDDLEWARE_API_KEY:
            raise ApiError(
                401,
                "invalid_api_key",
                "The X-Api-Key header is missing or invalid.",
            )

    token = _extract_bearer_token(request.headers.get("Authorization"))
    if not token:
        if REQUIRE_FIREBASE_AUTH:
            raise ApiError(
                401,
                "missing_bearer_token",
                "A Firebase ID token is required in the Authorization header.",
            )
        user_id = str(payload.get("user_id", "")).strip()
        if not user_id:
            raise ApiError(
                400,
                "missing_user_id",
                "Provide user_id in the request body when Firebase auth is disabled.",
            )
        return _validate_user_id(user_id)

    try:
        _ensure_firebase_initialized()
        decoded_token = firebase_auth.verify_id_token(token)
    except Exception as exc:
        raise ApiError(
            401,
            "invalid_firebase_token",
            "The Firebase ID token could not be verified.",
            {"reason": str(exc)},
        ) from exc

    token_user_id = _validate_user_id(str(decoded_token["uid"]))
    requested_user_id = str(payload.get("user_id", "")).strip()
    if requested_user_id and requested_user_id != token_user_id:
        raise ApiError(
            403,
            "user_id_mismatch",
            "The authenticated Firebase user does not match the supplied user_id.",
        )
    return token_user_id


def _validate_user_id(user_id: str) -> str:
    cleaned = user_id.strip()
    if not cleaned:
        raise ApiError(400, "invalid_user_id", "user_id must not be empty.")
    if len(cleaned) > 128:
        raise ApiError(
            400,
            "invalid_user_id",
            "user_id must be 128 characters or fewer.",
        )
    return cleaned


def _validate_thread_id(thread_id: str | None) -> str:
    if not thread_id:
        return f"thread-{uuid.uuid4().hex}"
    cleaned = thread_id.strip()
    if not cleaned:
        return f"thread-{uuid.uuid4().hex}"
    if len(cleaned) > 128:
        raise ApiError(
            400,
            "invalid_thread_id",
            "thread_id must be 128 characters or fewer.",
        )
    return cleaned


def _validate_session_id(session_id: Any) -> str | None:
    if session_id is None:
        return None
    cleaned = str(session_id).strip()
    if not cleaned:
        return None
    if len(cleaned) > 256:
        raise ApiError(
            400,
            "invalid_session_id",
            "session_id must be 256 characters or fewer.",
        )
    return cleaned


def _validate_message(message: Any) -> str:
    if not isinstance(message, str):
        raise ApiError(400, "invalid_message", "message must be a string.")
    cleaned = message.strip()
    if not cleaned:
        raise ApiError(400, "invalid_message", "message must not be empty.")
    if len(cleaned) > MAX_MESSAGE_CHARS:
        raise ApiError(
            400,
            "message_too_large",
            f"message exceeds MAX_MESSAGE_CHARS={MAX_MESSAGE_CHARS}.",
        )
    return cleaned


def _session_document_id(user_id: str, thread_id: str) -> str:
    return f"{user_id}__{thread_id}"


def _session_document(user_id: str, thread_id: str):
    return _get_firestore_client().collection(FIRESTORE_COLLECTION).document(
        _session_document_id(user_id, thread_id)
    )


def _load_session_record(user_id: str, thread_id: str) -> dict[str, Any] | None:
    snapshot = _session_document(user_id, thread_id).get()
    if not snapshot.exists:
        return None
    data = snapshot.to_dict() or {}
    data["thread_id"] = thread_id
    data["user_id"] = user_id
    return data


def _save_session_record(
    *,
    user_id: str,
    thread_id: str,
    session_id: str,
    session_payload: dict[str, Any],
) -> None:
    _session_document(user_id, thread_id).set(
        {
            "user_id": user_id,
            "thread_id": thread_id,
            "session_id": session_id,
            "agent_resource_name": AGENT_RESOURCE_NAME,
            "session_payload": session_payload,
            "updated_at": firestore.SERVER_TIMESTAMP,
        },
        merge=True,
    )


def _parse_upstream_error(response: RequestsResponse) -> dict[str, Any]:
    try:
        parsed = response.json()
    except ValueError:
        parsed = {"raw": response.text}
    return {
        "status_code": response.status_code,
        "body": parsed,
    }


def _post_agent_json(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        response = _get_authorized_session().post(
            AGENT_QUERY_URL,
            json=payload,
            timeout=(UPSTREAM_CONNECT_TIMEOUT_SECONDS, UPSTREAM_READ_TIMEOUT_SECONDS),
        )
    except requests_exceptions.RequestException as exc:
        raise ApiError(
            502,
            "agent_runtime_unreachable",
            "The middleware could not reach Agent Runtime.",
            {"reason": str(exc)},
        ) from exc

    if not response.ok:
        raise ApiError(
            502,
            "agent_runtime_error",
            "Agent Runtime returned a non-success response.",
            _parse_upstream_error(response),
        )

    try:
        return response.json()
    except ValueError as exc:
        raise ApiError(
            502,
            "invalid_agent_runtime_json",
            "Agent Runtime returned invalid JSON.",
            {"body": response.text},
        ) from exc


def _open_agent_stream(payload: dict[str, Any]) -> RequestsResponse:
    try:
        response = _get_authorized_session().post(
            AGENT_STREAM_QUERY_URL,
            json=payload,
            stream=True,
            timeout=(UPSTREAM_CONNECT_TIMEOUT_SECONDS, UPSTREAM_READ_TIMEOUT_SECONDS),
        )
    except requests_exceptions.RequestException as exc:
        raise ApiError(
            502,
            "agent_runtime_stream_unreachable",
            "The middleware could not open a streaming connection to Agent Runtime.",
            {"reason": str(exc)},
        ) from exc

    if not response.ok:
        response.close()
        raise ApiError(
            502,
            "agent_runtime_stream_error",
            "Agent Runtime returned a non-success response for streamQuery.",
            _parse_upstream_error(response),
        )
    return response


def _create_agent_session(user_id: str) -> dict[str, Any]:
    response = _post_agent_json(
        {
            "class_method": "async_create_session",
            "input": {"user_id": user_id},
        }
    )
    session_payload = response.get("output", response)
    session_id = session_payload.get("id")
    if not session_id:
        raise ApiError(
            502,
            "missing_session_id",
            "Agent Runtime did not return a session id.",
            {"response": response},
        )
    return session_payload


def _ensure_session(
    *,
    user_id: str,
    thread_id: str,
    requested_session_id: str | None = None,
    force_new_session: bool = False,
) -> dict[str, Any]:
    if not force_new_session:
        if requested_session_id:
            return {
                "user_id": user_id,
                "thread_id": thread_id,
                "session_id": requested_session_id,
                "session_payload": None,
                "agent_resource_name": AGENT_RESOURCE_NAME,
            }
        existing = _load_session_record(user_id, thread_id)
        if existing and existing.get("session_id"):
            return existing

    session_payload = _create_agent_session(user_id)
    session_id = str(session_payload["id"])
    _save_session_record(
        user_id=user_id,
        thread_id=thread_id,
        session_id=session_id,
        session_payload=session_payload,
    )
    return {
        "user_id": user_id,
        "thread_id": thread_id,
        "session_id": session_id,
        "session_payload": session_payload,
        "agent_resource_name": AGENT_RESOURCE_NAME,
    }


def _iter_sse_messages(response: RequestsResponse) -> Iterator[tuple[str | None, str]]:
    event_name: str | None = None
    data_lines: list[str] = []

    try:
        for line in response.iter_lines(decode_unicode=True):
            if line is None:
                continue
            if line == "":
                if data_lines:
                    yield event_name, "\n".join(data_lines)
                    event_name = None
                    data_lines = []
                continue
            if line.startswith(":"):
                continue
            if line.startswith("event:"):
                event_name = line.partition(":")[2].strip() or None
                continue
            if line.startswith("data:"):
                data_lines.append(line.partition(":")[2].strip())
                continue

            # Some Agent Runtime responses arrive as raw JSON lines instead of
            # explicit SSE "data:" fields. Treat those as data frames too.
            data_lines.append(line.strip())

        if data_lines:
            yield event_name, "\n".join(data_lines)
    finally:
        response.close()


def _extract_text_fragments(event_payload: dict[str, Any]) -> list[str]:
    fragments: list[str] = []

    def collect_parts(container: dict[str, Any] | None) -> None:
        if not isinstance(container, dict):
            return
        parts = container.get("parts")
        if not isinstance(parts, list):
            return
        for part in parts:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                fragments.append(part["text"])

    def walk(value: Any) -> None:
        if isinstance(value, list):
            for item in value:
                walk(item)
            return

        if not isinstance(value, dict):
            return

        output = value.get("output")
        if isinstance(output, str):
            fragments.append(output)

        role = value.get("role")
        if role == "model":
            collect_parts(value)

        content = value.get("content")
        if isinstance(content, dict):
            if content.get("role") == "model":
                collect_parts(content)
            walk(content)

        for nested_key in (
            "result",
            "event",
            "message",
            "response",
            "data",
            "value",
            "payload",
            "output",
        ):
            nested_value = value.get(nested_key)
            if isinstance(nested_value, (dict, list)):
                walk(nested_value)

    walk(event_payload)

    deduped_fragments: list[str] = []
    seen: set[str] = set()
    for fragment in fragments:
        if fragment not in seen:
            seen.add(fragment)
            deduped_fragments.append(fragment)
    return deduped_fragments


def _collect_streamed_response(
    response: RequestsResponse,
    *,
    include_events: bool,
) -> tuple[str, list[dict[str, Any]]]:
    text_fragments: list[str] = []
    events: list[dict[str, Any]] = []
    raw_messages: list[str] = []

    for _, data in _iter_sse_messages(response):
        if not data or data == "[DONE]":
            continue
        raw_messages.append(data)
        try:
            parsed = json.loads(data)
        except json.JSONDecodeError:
            LOGGER.warning(
                json.dumps(
                    {
                        "severity": "WARNING",
                        "event": "invalid_sse_payload",
                        "payload": data,
                    }
                )
            )
            continue

        if include_events:
            events.append(parsed)

        text_fragments.extend(_extract_text_fragments(parsed))

    if text_fragments:
        return "".join(text_fragments).strip(), events

    # Fallback for payloads that were returned as one JSON body or as a group
    # of concatenated JSON lines that did not match the first-pass extraction.
    for raw_message in raw_messages:
        candidate_payloads: list[Any] = []

        try:
            candidate_payloads.append(json.loads(raw_message))
        except json.JSONDecodeError:
            for line in raw_message.splitlines():
                stripped = line.strip()
                if not stripped or stripped == "[DONE]":
                    continue
                try:
                    candidate_payloads.append(json.loads(stripped))
                except json.JSONDecodeError:
                    continue

        for candidate in candidate_payloads:
            if include_events:
                if isinstance(candidate, list):
                    events.extend(
                        item for item in candidate if isinstance(item, dict)
                    )
                elif isinstance(candidate, dict):
                    events.append(candidate)

            if isinstance(candidate, dict):
                text_fragments.extend(_extract_text_fragments(candidate))
            elif isinstance(candidate, list):
                for item in candidate:
                    if isinstance(item, dict):
                        text_fragments.extend(_extract_text_fragments(item))

    return "".join(text_fragments).strip(), events


def _handle_health(origin: str | None) -> tuple[str, int, dict[str, str]]:
    return _json_response(
        {
            "ok": True,
            "service": "ceoagent-middleware",
            "agent_resource_name": AGENT_RESOURCE_NAME,
            "agent_region": AGENT_REGION,
            "firestore_collection": FIRESTORE_COLLECTION,
            "firebase_auth_required": REQUIRE_FIREBASE_AUTH,
        },
        200,
        origin,
    )


def _handle_create_session(
    request,
    payload: dict[str, Any],
    origin: str | None,
) -> tuple[str, int, dict[str, str]]:
    user_id = _authenticate_request(request, payload)
    thread_id = _validate_thread_id(payload.get("thread_id"))
    force_new_session = _parse_bool(payload.get("force_new_session"), default=False)
    session_record = _ensure_session(
        user_id=user_id,
        thread_id=thread_id,
        requested_session_id=_validate_session_id(payload.get("session_id")),
        force_new_session=force_new_session,
    )
    return _json_response(
        {
            "ok": True,
            "user_id": user_id,
            "thread_id": thread_id,
            "session_id": session_record["session_id"],
            "agent_resource_name": AGENT_RESOURCE_NAME,
        },
        200,
        origin,
    )


def _build_chat_request(user_id: str, session_id: str, message: str) -> dict[str, Any]:
    return {
        "class_method": "async_stream_query",
        "input": {
            "user_id": user_id,
            "session_id": session_id,
            "message": message,
        },
    }


def _handle_chat(
    request,
    payload: dict[str, Any],
    origin: str | None,
) -> tuple[str, int, dict[str, str]]:
    user_id = _authenticate_request(request, payload)
    thread_id = _validate_thread_id(payload.get("thread_id"))
    message = _validate_message(payload.get("message"))
    include_events = _parse_bool(payload.get("include_events"), default=False)
    force_new_session = _parse_bool(payload.get("force_new_session"), default=False)

    session_record = _ensure_session(
        user_id=user_id,
        thread_id=thread_id,
        requested_session_id=_validate_session_id(payload.get("session_id")),
        force_new_session=force_new_session,
    )
    upstream_response = _open_agent_stream(
        _build_chat_request(
            user_id=user_id,
            session_id=str(session_record["session_id"]),
            message=message,
        )
    )
    reply_text, raw_events = _collect_streamed_response(
        upstream_response,
        include_events=include_events,
    )

    return _json_response(
        {
            "ok": True,
            "user_id": user_id,
            "thread_id": thread_id,
            "session_id": session_record["session_id"],
            "reply_text": reply_text,
            "events": raw_events if include_events else [],
        },
        200,
        origin,
    )


def _sse_proxy_generator(
    upstream_response: RequestsResponse,
    metadata: dict[str, Any],
) -> Iterator[str]:
    yield f"event: metadata\ndata: {json.dumps(metadata)}\n\n"
    try:
        for line in upstream_response.iter_lines(decode_unicode=True):
            if line is None:
                continue
            yield f"{line}\n"
    finally:
        upstream_response.close()


def _handle_stream_chat(
    request,
    payload: dict[str, Any],
    origin: str | None,
) -> Response:
    user_id = _authenticate_request(request, payload)
    thread_id = _validate_thread_id(payload.get("thread_id"))
    message = _validate_message(payload.get("message"))
    force_new_session = _parse_bool(payload.get("force_new_session"), default=False)

    session_record = _ensure_session(
        user_id=user_id,
        thread_id=thread_id,
        requested_session_id=_validate_session_id(payload.get("session_id")),
        force_new_session=force_new_session,
    )
    upstream_response = _open_agent_stream(
        _build_chat_request(
            user_id=user_id,
            session_id=str(session_record["session_id"]),
            message=message,
        )
    )

    headers = _build_cors_headers(origin)
    headers.update(
        {
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )
    return Response(
        _sse_proxy_generator(
            upstream_response,
            {
                "ok": True,
                "user_id": user_id,
                "thread_id": thread_id,
                "session_id": session_record["session_id"],
            },
        ),
        status=200,
        headers=headers,
    )


def _resolve_action(path: str, payload: dict[str, Any]) -> str:
    normalized_path = path.rstrip("/") or "/"
    if normalized_path in {"/health", "/healthz"}:
        return "health"
    if normalized_path in {"/session", "/v1/session"}:
        return "create_session"
    if normalized_path in {"/chat", "/v1/chat"}:
        return "chat"
    if normalized_path in {"/chat/stream", "/v1/chat/stream", "/stream"}:
        return "stream_chat"

    action = str(payload.get("action", "")).strip().lower()
    if action:
        return action
    if "message" in payload:
        return "chat"
    return "health" if normalized_path == "/" else "unknown"


@functions_framework.http
def hello_http(request):
    origin = request.headers.get("Origin")

    try:
        _check_origin(origin)

        if request.method == "OPTIONS":
            return "", 204, _build_cors_headers(origin)

        if request.method == "GET":
            return _handle_health(origin)

        if request.method != "POST":
            raise ApiError(
                405,
                "method_not_allowed",
                "Only GET, POST, and OPTIONS are supported.",
            )

        payload = request.get_json(silent=True)
        if payload is None:
            payload = {}
        if not isinstance(payload, dict):
            raise ApiError(
                400,
                "invalid_json",
                "The request body must be a JSON object.",
            )

        action = _resolve_action(request.path, payload)
        LOGGER.info(
            json.dumps(
                {
                    "severity": "INFO",
                    "event": "incoming_request",
                    "path": request.path,
                    "action": action,
                }
            )
        )

        if action == "health":
            return _handle_health(origin)
        if action in {"create_session", "session"}:
            return _handle_create_session(request, payload, origin)
        if action == "chat":
            if _parse_bool(payload.get("stream"), default=False):
                return _handle_stream_chat(request, payload, origin)
            return _handle_chat(request, payload, origin)
        if action in {"stream_chat", "chat_stream"}:
            return _handle_stream_chat(request, payload, origin)

        raise ApiError(
            404,
            "unknown_action",
            "Use /chat, /chat/stream, /session, /health, or set action in the JSON body.",
            {"path": request.path, "action": action},
        )
    except ApiError as exc:
        return _error_response(exc, origin)
    except Exception as exc:
        LOGGER.exception("Unhandled middleware error")
        return _error_response(
            ApiError(
                500,
                "internal_error",
                "The middleware encountered an unexpected error.",
                {"reason": str(exc)},
            ),
            origin,
        )
