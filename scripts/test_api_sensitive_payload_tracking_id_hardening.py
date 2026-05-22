from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from typing import Any
from token_payments.api import ApiRequest, ApiAuthContext
from token_payments.api.auth import AuthApi
from token_payments.api.orders import OrdersApi
from token_payments.api.payments import PaymentsApi
from token_payments.contexts.auth.domain import AuthSession, IssuedToken, User, RefreshTokenHash, SessionId
from token_payments.contexts.order.application import OrderCreationResult
from token_payments.contexts.order.domain import Order, TrackingId, OrderStatus, Address
from token_payments.contexts.auth.domain.wallet import WalletId
from token_payments.contexts.payment.application import PaymentCommandResult, PaymentCommandStatus
from token_payments.contexts.payment.domain import Payment, PaymentStatus
from token_payments.shared.domain import OrderId, PaymentId, UserId, CustomerId, StoreId, WalletAddress, CommandId, ChainNetwork, Crypto



class FakeAuthUseCase:
    def loginWithMetaMask(self, command: Any) -> Any:
        session = AuthSession(
            session_id=SessionId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c2b"),
            user_id=UserId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c2a"),
            login_wallet_id=WalletId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c2f"),
            wallet=WalletAddress("0x1111111111111111111111111111111111111111"),
            device_id="device-1",
            refresh_token_hash=RefreshTokenHash(hash="somehash", salt="salt", rotation_version=1),
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
        user = User(
            user_id=UserId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c2a"),
            primary_wallet=WalletAddress("0x1111111111111111111111111111111111111111"),
            active=True,
            last_login_at=datetime.now(UTC),
        )
        issued_token = IssuedToken(
            access_token="access-tok",
            refresh_token="refresh-tok",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        from token_payments.contexts.auth.application import LoginResult
        return LoginResult(user=user, session=session, issued_token=issued_token)


class FakeProductSnapshot:
    def __init__(self) -> None:
        self.product_id = "018f33aa-9e6d-73d8-9dc3-47d6cdcc6c25"
        self.name = "Test Product"
        self.price = Crypto(amount=Decimal("10.00"), symbol="USDC", chain_id=1, token_address=None, decimals=6)


class FakeOrderItem:
    def __init__(self) -> None:
        self.order_item_id = "018f33aa-9e6d-73d8-9dc3-47d6cdcc6c2e"
        self.product_snapshot = FakeProductSnapshot()
        self.quantity = 1
        self.sub_total = Crypto(amount=Decimal("10.00"), symbol="USDC", chain_id=1, token_address=None, decimals=6)


class FakeDeliveryAddress:
    def __init__(self) -> None:
        self.id = "addr-1"
        self.street = "123 Road"


class FakeOrder:
    def __init__(self) -> None:
        self.order_id = "018f33aa-9e6d-73d8-9dc3-47d6cdcc6c21"
        self.tracking_id = "018f33aa-9e6d-73d8-9dc3-47d6cdcc6c22"
        self.store_id = "018f33aa-9e6d-73d8-9dc3-47d6cdcc6c23"
        from token_payments.contexts.order.domain import OrderStatus
        self.status = OrderStatus.PENDING
        self.delivery_address = FakeDeliveryAddress()
        self.items = (FakeOrderItem(),)


class FakeOrderUseCase:
    def createOrder(self, command: Any) -> Any:
        order = FakeOrder()
        total_amount = Crypto(amount=Decimal("10.00"), symbol="USDC", chain_id=1, token_address=None, decimals=6)
        return OrderCreationResult(order=order, total_amount=total_amount, outbox_message=None)


class FakePaymentCommandHandler:
    def __init__(self) -> None:
        self.commands = []

    def submit_transaction_hash(self, command: Any) -> Any:
        self.commands.append(command)
        payment = Payment(
            payment_id=command.payment_id,
            order_id=command.order_id,
            customer_id=CustomerId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c24"),
            amount=Crypto(amount=Decimal("10.00"), symbol="USDC", chain_id=1, token_address=None, decimals=6),
            wallet_from=WalletAddress("0x1111111111111111111111111111111111111111"),
            wallet_to=WalletAddress("0x2222222222222222222222222222222222222222"),
            chain_network=ChainNetwork(chain_id=1, name="Ethereum"),
            gas_estimate=None,
            status=PaymentStatus.SUBMITTED,
            tx_hash=command.tx_hash,
            expires_at=datetime.now(UTC) + timedelta(minutes=15),
        )
        return PaymentCommandResult(
            command_id=command.command_id,
            order_id=command.order_id,
            status=PaymentCommandStatus.TX_SUBMITTED,
            payment=payment,
        )


class FakeTrackingQuery:
    def __init__(self, owner_user_id: str = "018f33aa-9e6d-73d8-9dc3-47d6cdcc6c2a") -> None:
        self.owner_user_id = owner_user_id

    def resolve_and_verify(self, tracking_id: TrackingId, user_id: UserId) -> tuple[OrderId, PaymentId]:
        if str(user_id) != self.owner_user_id:
            raise ValueError("authenticated user does not own the order")
        if str(tracking_id) == "not-found":
            raise ValueError("trackingId not-found not found")
        return OrderId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c21"), PaymentId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c25")


def test_session_payload_excludes_sensitive_keys() -> None:
    api = AuthApi(FakeAuthUseCase())
    req = ApiRequest(
        request_id="req-1",
        method="POST",
        path="/auth/sessions",
        body={
            "walletAddress": "0x1111111111111111111111111111111111111111",
            "message": "SIWE message",
            "signature": "0x...",
            "deviceId": "device-1",
        },
    )
    res = api.login_with_metamask(req)
    assert res.status_code == 200
    
    session_data = res.body["session"]
    # Check what IS returned
    assert "userId" in session_data
    assert "walletAddress" in session_data
    assert "deviceId" in session_data
    assert "expiresAt" in session_data
    
    # Check what IS NOT returned
    assert "sessionId" not in session_data
    assert "refreshTokenHash" not in session_data
    assert "hash" not in session_data
    assert "salt" not in session_data
    assert "rotationVersion" not in session_data


def test_order_creation_payload_excludes_sensitive_keys() -> None:
    api = OrdersApi(FakeOrderUseCase())
    req = ApiRequest(
        request_id="req-2",
        method="POST",
        path="/orders",
        headers={"X-User-Id": "018f33aa-9e6d-73d8-9dc3-47d6cdcc6c2a"},
        body={
            "storeId": "018f33aa-9e6d-73d8-9dc3-47d6cdcc6c23",
            "deliveryAddress": {"id": "addr-1", "street": "123 Road"},
            "items": [{"productId": "018f33aa-9e6d-73d8-9dc3-47d6cdcc6c25", "quantity": 1}],
        },
    )
    res = api.create_order(req)
    assert res.status_code == 201
    
    order_data = res.body["order"]
    # Check what IS returned
    assert "orderId" in order_data
    assert "trackingId" in order_data
    assert "publicStoreId" in order_data
    
    # Check what IS NOT returned
    assert "customerId" not in order_data
    assert "storeId" not in order_data


def test_payment_submission_validations() -> None:
    handler = FakePaymentCommandHandler()
    tracking_query = FakeTrackingQuery(owner_user_id="018f33aa-9e6d-73d8-9dc3-47d6cdcc6c2a")
    api = PaymentsApi(handler, tracking_query=tracking_query)

    # 1. Rejects orderId in body
    req_with_order = ApiRequest(
        request_id="req-p1",
        method="POST",
        path="/payments/transaction-hashes",
        body={
            "orderId": "018f33aa-9e6d-73d8-9dc3-47d6cdcc6c21",
            "trackingId": "018f33aa-9e6d-73d8-9dc3-47d6cdcc6c22",
            "txHash": "0x" + "ab" * 32,
        },
        auth_context=ApiAuthContext(user_id="018f33aa-9e6d-73d8-9dc3-47d6cdcc6c2a", session_id="018f33aa-9e6d-73d8-9dc3-47d6cdcc6c2b"),
    )
    res = api.submit_transaction_hash(req_with_order)
    assert res.status_code == 400
    assert res.body["error"]["code"] == "VALIDATION_ERROR"

    # 2. Rejects if session is missing
    req_no_auth = ApiRequest(
        request_id="req-p2",
        method="POST",
        path="/payments/transaction-hashes",
        body={
            "trackingId": "018f33aa-9e6d-73d8-9dc3-47d6cdcc6c22",
            "txHash": "0x" + "ab" * 32,
        },
    )
    res_no_auth = api.submit_transaction_hash(req_no_auth)
    assert res_no_auth.status_code == 400
    assert res_no_auth.body["error"]["code"] == "VALIDATION_ERROR"

    # 3. Fails with 403 if user does not own the order
    req_wrong_owner = ApiRequest(
        request_id="req-p3",
        method="POST",
        path="/payments/transaction-hashes",
        body={
            "trackingId": "018f33aa-9e6d-73d8-9dc3-47d6cdcc6c22",
            "txHash": "0x" + "ab" * 32,
        },
        auth_context=ApiAuthContext(user_id="018f33aa-9e6d-73d8-9dc3-47d6cdcc6c2c", session_id="018f33aa-9e6d-73d8-9dc3-47d6cdcc6c2d"),
    )
    res_wrong_owner = api.submit_transaction_hash(req_wrong_owner)
    assert res_wrong_owner.status_code == 403
    assert res_wrong_owner.body["error"]["code"] == "FORBIDDEN"

    # 4. Valid submit returning correct response payload
    tracking_id_str = "018f33aa-9e6d-73d8-9dc3-47d6cdcc6c22"
    tx_hash_str = "0x" + "ab" * 32
    req_valid = ApiRequest(
        request_id="req-p4",
        method="POST",
        path="/payments/transaction-hashes",
        body={
            "trackingId": tracking_id_str,
            "txHash": tx_hash_str,
        },
        auth_context=ApiAuthContext(user_id="018f33aa-9e6d-73d8-9dc3-47d6cdcc6c2a", session_id="018f33aa-9e6d-73d8-9dc3-47d6cdcc6c2b"),
    )
    res_valid = api.submit_transaction_hash(req_valid)
    assert res_valid.status_code == 202
    
    payment_data = res_valid.body["payment"]
    assert payment_data["trackingId"] == tracking_id_str
    assert payment_data["status"] == "TX_SUBMITTED"
    assert payment_data["txHash"] == tx_hash_str
    assert "orderId" not in payment_data

    # 5. Idempotency key fallback uses trackingId
    cmd = handler.commands[0]
    assert cmd.command_id == CommandId(f"payment.submit_tx:{tracking_id_str}")
