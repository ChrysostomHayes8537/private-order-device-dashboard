from __future__ import annotations

import os
from contextlib import asynccontextmanager
from enum import StrEnum
from typing import Annotated, Literal

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from .infrai_realtime import InfraiError, InfraiRealtime


class OrderStage(StrEnum):
    CHECKOUT_STARTED = "checkout_started"
    PAYMENT_ACCEPTED = "payment_accepted"
    FULFILLMENT_STARTED = "fulfillment_started"
    SHIPPED = "shipped"
    RECEIPT_READY = "receipt_ready"


class DeviceState(StrEnum):
    ONLINE = "online"
    BUSY = "busy"
    OFFLINE = "offline"


class OrderDeviceEvent(BaseModel):
    event_id: str = Field(min_length=8, max_length=80)
    account_id: str = Field(min_length=1, max_length=80)
    order_id: str = Field(min_length=1, max_length=80)
    stage: OrderStage
    device_kind: Literal["checkout_terminal", "warehouse_scanner", "receipt_printer"]
    device_state: DeviceState
    customer_reference: str | None = Field(default=None, max_length=80)
    receipt_reference: str | None = Field(default=None, max_length=80)


class PublishedUpdate(BaseModel):
    event_id: str
    order_id: str
    stage: OrderStage
    device_kind: str
    device_state: DeviceState
    customer_visible: bool


CUSTOMER_VISIBLE_STAGES = {
    OrderStage.PAYMENT_ACCEPTED,
    OrderStage.FULFILLMENT_STARTED,
    OrderStage.SHIPPED,
    OrderStage.RECEIPT_READY,
}


def dashboard_projection(source: OrderDeviceEvent) -> PublishedUpdate:
    return PublishedUpdate(
        event_id=source.event_id,
        order_id=source.order_id,
        stage=source.stage,
        device_kind=source.device_kind,
        device_state=source.device_state,
        customer_visible=source.stage in CUSTOMER_VISIBLE_STAGES,
    )


def build_app(client: InfraiRealtime, channel: str) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        client.create_channel(channel, f"setup-{channel}")
        try:
            yield
        finally:
            client.close()

    app = FastAPI(title="Private order device dashboard", lifespan=lifespan)

    @app.post("/orders/events", response_model=PublishedUpdate)
    def publish_order_event(
        source: OrderDeviceEvent,
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8)],
    ) -> PublishedUpdate:
        update = dashboard_projection(source)
        try:
            client.publish(
                channel=channel,
                event="order.device_status",
                data=update.model_dump(mode="json"),
                account_id=source.account_id,
                idempotency_key=idempotency_key,
            )
        except InfraiError as exc:
            client_status = exc.status_code if 400 <= exc.status_code < 500 else 502
            raise HTTPException(
                status_code=client_status,
                detail={"code": exc.code, "message": str(exc)},
            ) from exc
        return update

    @app.post("/dashboard/session")
    def dashboard_session(client_id: str) -> dict[str, object]:
        try:
            return client.issue_dashboard_token(client_id, channel)
        except InfraiError as exc:
            client_status = exc.status_code if 400 <= exc.status_code < 500 else 502
            raise HTTPException(
                status_code=client_status,
                detail={"code": exc.code, "message": str(exc)},
            ) from exc

    return app


def app_from_environment() -> FastAPI:
    api_key = os.environ["INFRAI_API_KEY"]
    channel = os.environ.get("INFRAI_CHANNEL", "shop-operations")
    return build_app(InfraiRealtime(api_key), channel)
