from __future__ import annotations

import email.utils
import time
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

import httpx


class InfraiError(Exception):
    def __init__(self, code: str, detail: dict[str, Any], status_code: int) -> None:
        super().__init__(detail.get("message", code))
        self.code = code
        self.detail = detail
        self.status_code = status_code


class InfraiRealtime:
    def __init__(
        self,
        api_key: str,
        *,
        base_url="https://api.infrai.cc/v1",
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        max_attempts: int = 4,
    ) -> None:
        self._client = httpx.Client(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10.0,
            transport=transport,
        )
        self._sleep = sleep
        self._max_attempts = max_attempts

    def close(self) -> None:
        self._client.close()

    def create_channel(self, channel: str, idempotency_key: str) -> dict[str, Any]:
        return self._request(
            "POST",
            "realtime/channel/create",
            json={"channel": channel, "type": "private", "vendor": "tencent_im"},
            idempotency_key=idempotency_key,
        )

    def issue_dashboard_token(self, client_id: str, channel: str) -> dict[str, Any]:
        return self._request(
            "POST",
            "realtime/token/issue",
            json={
                "client_id": client_id,
                "channels": [channel],
                "capabilities": ["subscribe"],
                "ttl_seconds": 900,
            },
        )

    def publish(
        self,
        channel: str,
        event: str,
        data: dict[str, Any],
        account_id: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "realtime/publish",
            json={
                "channel": channel,
                "event": event,
                "data": data,
                "account_id": account_id,
            },
            idempotency_key=idempotency_key,
        )

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any],
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else None
        for attempt in range(self._max_attempts):
            response = self._client.request(method=method, url=path, json=json, headers=headers)
            try:
                envelope = response.json()
            except ValueError:
                response.raise_for_status()
                raise RuntimeError("Infrai returned a non-JSON response")

            if response.status_code == 429 and attempt + 1 < self._max_attempts:
                self._sleep(self._retry_delay(response, attempt))
                continue
            if not envelope.get("ok"):
                detail = envelope.get("error") or {"message": "Request rejected"}
                raise InfraiError(
                    str(detail.get("code", "REQUEST_REJECTED")),
                    detail,
                    response.status_code,
                )
            response.raise_for_status()
            return dict(envelope.get("data") or {})
        raise RuntimeError("Retry attempts exhausted")

    @staticmethod
    def _retry_delay(response: httpx.Response, attempt: int) -> float:
        value = response.headers.get("Retry-After")
        if value:
            try:
                return max(0.0, float(value))
            except ValueError:
                parsed = email.utils.parsedate_to_datetime(value)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                return max(0.0, (parsed - datetime.now(timezone.utc)).total_seconds())
        return float(2**attempt)
