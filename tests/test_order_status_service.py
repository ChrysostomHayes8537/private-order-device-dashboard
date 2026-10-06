import json

import httpx
from fastapi.testclient import TestClient

from order_dashboard.infrai_realtime import InfraiRealtime
from order_dashboard.order_status_service import build_app


def test_receipt_event_publishes_only_dashboard_safe_fields() -> None:
    captured: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/realtime/channel/create"):
            assert json.loads(request.content) == {
                "channel": "shop-operations", "type": "private", "vendor": "tencent_im"
            }
            assert request.headers["Idempotency-Key"] == "setup-shop-operations"
            return httpx.Response(200, json={"ok": True, "data": {"channel": "shop-operations"}})
        captured.append(json.loads(request.content))
        return httpx.Response(200, json={"ok": True, "data": {"published": True}})

    realtime = InfraiRealtime("test-key", transport=httpx.MockTransport(handler))
    app = build_app(realtime, "shop-operations")

    with TestClient(app) as service:
        response = service.post(
            "/orders/events",
            headers={"Idempotency-Key": "evt-receipt-1042"},
            json={
                "event_id": "evt-1042",
                "account_id": "clinic-shop-7",
                "order_id": "ord-1042",
                "stage": "receipt_ready",
                "device_kind": "receipt_printer",
                "device_state": "online",
                "customer_reference": "patient-8841",
                "receipt_reference": "receipt-private-1042",
            },
        )

    assert response.status_code == 200
    assert response.json()["customer_visible"] is True
    assert captured == [
        {
            "channel": "shop-operations",
            "event": "order.device_status",
            "data": {
                "event_id": "evt-1042",
                "order_id": "ord-1042",
                "stage": "receipt_ready",
                "device_kind": "receipt_printer",
                "device_state": "online",
                "customer_visible": True,
            },
            "account_id": "clinic-shop-7",
        }
    ]


def test_rate_limit_honors_retry_after_without_changing_idempotency_key() -> None:
    keys: list[str | None] = []
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        keys.append(request.headers.get("Idempotency-Key"))
        if len(keys) == 1:
            return httpx.Response(
                429,
                headers={"Retry-After": "2"},
                json={"ok": False, "error": {"code": "RATE_LIMITED"}},
            )
        return httpx.Response(200, json={"ok": True, "data": {"published": True}})

    realtime = InfraiRealtime(
        "test-key",
        transport=httpx.MockTransport(handler),
        sleep=sleeps.append,
    )
    realtime.publish(
        "shop-operations",
        "order.device_status",
        {"order_id": "ord-1042"},
        "clinic-shop-7",
        "evt-retry-1042",
    )

    assert sleeps == [2.0]
    assert keys == ["evt-retry-1042", "evt-retry-1042"]
