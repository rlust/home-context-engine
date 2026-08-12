"""Least-privilege loopback HTTP receiver for Home Context snapshots."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable

from .normalizer import NormalizerState, SnapshotError, normalize_and_append, validate_snapshot


RECEIVER_PATH = "/v1/home-context/snapshot"
SECRET_HEADER = "X-Home-Context-Secret"
MAX_BODY_BYTES = 65_536
MAX_SKEW_SECONDS = 600
READ_TIMEOUT_SECONDS = 5
MIN_SECRET_BYTES = 32


class ReceiverError(ValueError):
    """Safe request-boundary failure with no private values in its message."""


def require_loopback_bind(host: str) -> str:
    if host != "127.0.0.1":
        raise ReceiverError("receiver bind address must be explicit IPv4 loopback 127.0.0.1")
    return host


class ReplayStore:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path, check_same_thread=False)
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS accepted_requests (
                fingerprint TEXT PRIMARY KEY,
                accepted_at TEXT NOT NULL
            )
            """
        )
        self.connection.commit()
        os.chmod(path, 0o600)

    def contains(self, fingerprint: str) -> bool:
        return self.connection.execute(
            "SELECT 1 FROM accepted_requests WHERE fingerprint = ?", (fingerprint,)
        ).fetchone() is not None

    def add(self, fingerprint: str, accepted_at: str) -> None:
        self.connection.execute(
            "INSERT OR IGNORE INTO accepted_requests(fingerprint, accepted_at) VALUES (?, ?)",
            (fingerprint, accepted_at),
        )
        self.connection.commit()

    def prune_before(self, cutoff: str) -> None:
        self.connection.execute(
            "DELETE FROM accepted_requests WHERE julianday(accepted_at) < julianday(?)", (cutoff,)
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()


class SnapshotReceiver:
    def __init__(
        self,
        *,
        secret: str,
        replay_database: Path,
        normalizer_database: Path,
        output: Path,
        now: Callable[[], datetime] | None = None,
    ):
        encoded_secret = secret.encode("utf-8")
        if len(encoded_secret) < MIN_SECRET_BYTES:
            raise ReceiverError("receiver secret must contain at least 32 bytes")
        paths = {replay_database.resolve(), normalizer_database.resolve(), output.resolve()}
        if len(paths) != 3:
            raise ReceiverError("replay, normalizer-state, and output paths must be distinct")
        self._secret = encoded_secret
        self._replay = ReplayStore(replay_database)
        self._normalizer_database = normalizer_database
        self._output = output
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._request_lock = threading.Lock()

    def close(self) -> None:
        self._replay.close()

    def receive(self, *, supplied_secret: str | None, body: bytes) -> tuple[int, dict[str, Any]]:
        if supplied_secret is None or not hmac.compare_digest(
            supplied_secret.encode("utf-8"), self._secret
        ):
            return 401, {"status": "rejected", "reason": "authentication_failed"}
        if not self._request_lock.acquire(blocking=False):
            return 503, {"status": "unavailable", "reason": "backpressure"}
        try:
            return self._receive_locked(body)
        finally:
            self._request_lock.release()

    def _receive_locked(self, body: bytes) -> tuple[int, dict[str, Any]]:
        fingerprint = hashlib.sha256(body).hexdigest()
        try:
            snapshot = json.loads(body.decode("utf-8"))
            snapshot = validate_snapshot(snapshot)
            snapshot_at = datetime.fromisoformat(
                snapshot["snapshot_at"].replace("Z", "+00:00")
            ).astimezone(timezone.utc)
            now_value = self._now()
            if now_value.tzinfo is None:
                raise ReceiverError("receiver clock must include a timezone")
            now = now_value.astimezone(timezone.utc)
            if abs((now - snapshot_at).total_seconds()) > MAX_SKEW_SECONDS:
                raise ReceiverError("snapshot timestamp is outside the allowed skew")
            replay_cutoff = (now - timedelta(seconds=2 * MAX_SKEW_SECONDS)).isoformat().replace(
                "+00:00", "Z"
            )
            self._replay.prune_before(replay_cutoff)
            if self._replay.contains(fingerprint):
                return 200, {"status": "duplicate", "reason": "replay"}
            with NormalizerState(self._normalizer_database) as state:
                result = normalize_and_append(snapshot, state, self._output)
        except (UnicodeDecodeError, json.JSONDecodeError, SnapshotError, ReceiverError, ValueError):
            return 422, {"status": "rejected", "reason": "invalid_snapshot"}
        except (OSError, sqlite3.Error):
            return 503, {"status": "unavailable", "reason": "local_storage"}
        accepted_at = now.isoformat().replace("+00:00", "Z")
        try:
            self._replay.add(fingerprint, accepted_at)
        except sqlite3.Error:
            return 503, {"status": "unavailable", "reason": "local_storage"}
        if result["records"] == 0:
            return 200, {"status": "duplicate", "reason": "no_transition"}
        return 202, {
            "status": "accepted",
            "prediction_created": result["prediction_created"],
            "feedback_created": result["feedback_created"],
            "audit_visible": bool(
                result["feedback_audit_failures"] or not result["counter_audit_consistent"]
            ),
        }


def make_handler(receiver: SnapshotReceiver) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def handle(self) -> None:
            try:
                super().handle()
            except (OSError, TimeoutError):
                return

        def setup(self) -> None:
            super().setup()
            self.connection.settimeout(READ_TIMEOUT_SECONDS)

        def do_POST(self) -> None:  # noqa: N802
            if self.path != RECEIVER_PATH:
                self._respond(404, {"status": "rejected", "reason": "not_found"})
                return
            content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
            if content_type != "application/json":
                self._respond(415, {"status": "rejected", "reason": "content_type"})
                return
            try:
                length = int(self.headers.get("Content-Length", ""))
            except ValueError:
                self._respond(411, {"status": "rejected", "reason": "content_length"})
                return
            if length < 1 or length > MAX_BODY_BYTES:
                self._respond(413, {"status": "rejected", "reason": "body_size"})
                return
            try:
                body = self.rfile.read(length)
            except (OSError, TimeoutError):
                self._respond(408, {"status": "unavailable", "reason": "request_timeout"})
                return
            if len(body) != length:
                self._respond(400, {"status": "rejected", "reason": "incomplete_body"})
                return
            code, payload = receiver.receive(
                supplied_secret=self.headers.get(SECRET_HEADER), body=body
            )
            self._respond(code, payload)

        def _method_not_allowed(self) -> None:
            self._respond(405, {"status": "rejected", "reason": "method_not_allowed"})

        do_GET = do_PUT = do_PATCH = do_DELETE = _method_not_allowed

        def _respond(self, code: int, payload: dict[str, Any]) -> None:
            body = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()
            self.close_connection = True
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            try:
                self.wfile.write(body)
            except OSError:
                return

        def log_message(self, _format: str, *_args: object) -> None:
            return

    return Handler


def build_server(host: str, port: int, receiver: SnapshotReceiver) -> ThreadingHTTPServer:
    require_loopback_bind(host)
    if not 0 <= port <= 65535:
        raise ReceiverError("receiver port must be from 0 to 65535")
    server = ThreadingHTTPServer((host, port), make_handler(receiver))
    server.daemon_threads = False
    server.block_on_close = True
    return server
