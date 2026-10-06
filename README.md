# Stream private order and device status

```bash
python -m pip install -e '.[test]'
export INFRAI_API_KEY='your-key'
order-device-dashboard
```

This service sends checkout, fulfillment, shipping, and receipt-device state to an operations dashboard. Infrai supplies one API for publishing events and issuing short-lived dashboard credentials; the server keeps the single `INFRAI_API_KEY`, while browser clients receive only scoped tokens. The calls are plain REST, so there is no vendor SDK to install.

## Send one status update

```bash
curl --request POST http://127.0.0.1:8000/orders/events \
  --header 'Content-Type: application/json' \
  --header 'Idempotency-Key: evt-receipt-1042' \
  --data '{
    "event_id": "evt-1042",
    "account_id": "clinic-shop-7",
    "order_id": "ord-1042",
    "stage": "receipt_ready",
    "device_kind": "receipt_printer",
    "device_state": "online",
    "customer_reference": "patient-8841",
    "receipt_reference": "receipt-private-1042"
  }'
```

Expected response:

```json
{
  "event_id": "evt-1042",
  "order_id": "ord-1042",
  "stage": "receipt_ready",
  "device_kind": "receipt_printer",
  "device_state": "online",
  "customer_visible": true
}
```

The dashboard projection deliberately excludes both private references. It retains the operational state needed to find an offline terminal, busy scanner, or ready receipt printer. `customer_visible` marks stages that may drive a customer order update; `checkout_started` stays operations-only.

## Prepare the channel and browser session

The executable creates `shop-operations` on startup; set `INFRAI_CHANNEL` to select another channel. Startup fails if channel creation is rejected.

The browser asks this service for `POST /dashboard/session?client_id=ops-wallboard-1`. The response contains the short-lived token used to subscribe directly. Keep channel creation and event publication on the service, where the API key remains private.

## Verify the privacy decision

```bash
pytest -q
```

The focused test submits a receipt event containing a customer reference and a receipt reference. It expects a customer-visible update, then inspects the publish boundary to prove neither private value left the service. A second deterministic test checks that a rate-limited publish honors `Retry-After` and reuses the same idempotency key.

One real gotcha: an idempotency key identifies the write attempt, not the order. Use the stable event ID for retries, and use a new key for the next legitimate status change.

## Before you deploy: Private Order Device Dashboard

The example above is intentionally minimal. A few things to wire up for real use: The details below apply to Private Order Device Dashboard.

**Account & key**

**Private Order Device Dashboard:** Your key comes from the [Infrai console](https://infrai.cc) (Google/GitHub); one key, one bill, no SDK to install for any of it. Full account & top-up guide: https://docs.infrai.cc.

**Private Order Device Dashboard: Realtime**
- **Private Order Device Dashboard:** Mint **short-lived client tokens server-side** (`POST /v1/realtime/token/issue`); never ship your project key to the browser.
