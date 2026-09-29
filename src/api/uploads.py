"""Intake byte-limit boundary for multipart claim uploads (SR-009).

Two enforcement layers share the same configured caps: ASGI middleware refuses
an over-declared Content-Length before FastAPI's multipart parser buffers or
spools anything, and ``write_upload_stream`` copies each part in bounded chunks
while counting bytes against the per-file and running-request allowances.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, MutableMapping
from pathlib import Path
from typing import Any

from starlette.datastructures import UploadFile

# 64 KiB blocks keep peak memory independent of upload size (P-05).
_CHUNK_SIZE = 64 * 1024

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]


class UploadTooLargeError(ValueError):
    """A multipart part or the whole request exceeded a configured byte cap."""

    def __init__(self, reason: str, field: str = "") -> None:
        """Build the oversized-upload message from the stable reason code.

        :param reason: Snake_case detail ``file_too_large`` or ``request_too_large``.
        :param field: Multipart field name when known (optional).
        """
        self.reason = reason
        self.field = field
        detail = f"upload too large: {reason}"
        if field:
            detail = f"{detail} ({field})"
        super().__init__(detail)


def write_upload_stream(
    upload: UploadFile,
    dest: Path,
    *,
    max_file_bytes: int,
    remaining_bytes: int,
) -> int:
    """Copy one upload to disk in bounded chunks under the configured caps.

    The count is checked per block rather than from a declared size because a
    client controls both the declared size and the stream.

    :param upload: Starlette/FastAPI upload whose ``.file`` is streamed.
    :param dest: Destination path under the claim directory.
    :param max_file_bytes: Per-part byte cap from ``api.upload``.
    :param remaining_bytes: Bytes still allowed for this request total.
    :return: Number of bytes written.
    :raises UploadTooLargeError: When the stream passes either cap; the partial
        destination is unlinked before the error leaves.
    """
    field = upload.filename or ""

    def _ensure_within_caps(written: int) -> None:
        if written > max_file_bytes:
            raise UploadTooLargeError("file_too_large", field=field)
        if written > remaining_bytes:
            raise UploadTooLargeError("request_too_large", field=field)

    written = 0
    try:
        with dest.open("wb") as out:
            while True:
                chunk = upload.file.read(_CHUNK_SIZE)
                if not chunk:
                    break
                written += len(chunk)
                _ensure_within_caps(written)
                out.write(chunk)
    except UploadTooLargeError:
        dest.unlink(missing_ok=True)
        raise
    return written


class UploadSizeLimitMiddleware:
    """Refuse HTTP requests whose declared Content-Length exceeds the request cap.

    Exists as middleware rather than a handler check because FastAPI parses the
    multipart body before handler code runs, so a handler-level check cannot
    prevent the buffering this cap exists to prevent.
    """

    def __init__(self, app: ASGIApp, max_request_bytes: int) -> None:
        """Bind the inner ASGI app and the configured request byte cap.

        :param app: Downstream ASGI application.
        :param max_request_bytes: Cap from ``api.upload.max_request_bytes``.
        """
        self.app = app
        self.max_request_bytes = max_request_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Reject oversized declared bodies; otherwise delegate unchanged.

        :param scope: ASGI connection scope.
        :param receive: ASGI receive callable.
        :param send: ASGI send callable.
        """
        if scope["type"] == "http":
            content_length = _declared_content_length(scope)
            if content_length is not None and content_length > self.max_request_bytes:
                body = json.dumps({"detail": "request_too_large"}).encode("utf-8")
                await send({
                    "type": "http.response.start",
                    "status": 413,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(body)).encode("ascii")),
                    ],
                })
                await send({"type": "http.response.body", "body": body})
                return
        await self.app(scope, receive, send)


def _declared_content_length(scope: Scope) -> int | None:
    """Parse the Content-Length header from an HTTP scope when present.

    :param scope: ASGI HTTP scope.
    :return: Declared length, or None when absent or unparsable.
    """
    for key, value in scope.get("headers", []):
        if key == b"content-length":
            try:
                return int(value.decode("latin-1"))
            except ValueError:
                return None
    return None
