from decimal import Decimal

from unittest.mock import MagicMock, create_autospec, patch
import pytest
from django.utils import timezone
from datetime import timedelta

from resources.models import Reservation

from ..exceptions import OrderStateTransitionError
from ..factories import OrderFactory
from ..models import Order, OrderLogEntry

from ..providers.base import PaymentProvider


@pytest.fixture(autouse=True)
def auto_use_django_db(db):
    pass


@pytest.fixture
def mock_payment_provider():
    mocked_provider = create_autospec(PaymentProvider)
    mocked_provider.initiate_payment = MagicMock(
        return_value="https://mocked-payment-url.com"
    )
    with patch("payments.providers.get_payment_provider", return_value=mocked_provider):
        yield mocked_provider


@pytest.mark.parametrize(
    ",".join(
        (
            "order_state",
            "reservation_state",
            "requested_at",
            "approved_at",
            "order_created",
            "expired",
        )
    ),
    [
        # Reservation requested + expired order: ignore
        (
            Order.EXPIRED,
            Reservation.REQUESTED,
            timedelta(days=5),
            None,
            timedelta(days=5),
            False,
        ),
        # Reservation requested < 3 days ago: ignore
        (
            Order.WAITING,
            Reservation.REQUESTED,
            timedelta(days=1),
            None,
            timedelta(days=1),
            False,
        ),
        # Reservation requested > 3 days ago: expire
        (
            Order.WAITING,
            Reservation.REQUESTED,
            timedelta(days=5),
            None,
            timedelta(days=5),
            True,
        ),
        # Reservation waiting for payment, order expired: ignore
        (
            Order.EXPIRED,
            Reservation.WAITING_FOR_PAYMENT,
            timedelta(days=3),
            None,
            timedelta(minutes=20),
            False,
        ),
        # Reservation waiting for payment, approved > 24 hours ago: expire
        (
            Order.WAITING,
            Reservation.WAITING_FOR_PAYMENT,
            None,
            timedelta(days=3),
            timedelta(days=3),
            True,
        ),
        # Reservation waiting for payment, approved < 24 hours ago: ignore
        (
            Order.WAITING,
            Reservation.WAITING_FOR_PAYMENT,
            None,
            timedelta(hours=10),
            timedelta(hours=10),
            False,
        ),
        # Reservation waiting for payment, created < max payment time: ignore
        (
            Order.WAITING,
            Reservation.WAITING_FOR_PAYMENT,
            None,
            None,
            timedelta(minutes=10),
            False,
        ),
        # Reservation waiting for payment, created > max payment time: expire
        (
            Order.WAITING,
            Reservation.WAITING_FOR_PAYMENT,
            None,
            None,
            timedelta(minutes=20),
            True,
        ),
    ],
)
def test_update_expired(
    settings,
    mock_payment_provider,
    resource_with_opening_hours,
    user,
    order_state,
    reservation_state,
    approved_at,
    requested_at,
    order_created,
    expired,
):
    # 15 minutes
    settings.RESPA_PAYMENTS_PAYMENT_WAITING_TIME = 15

    now = timezone.now()

    reservation = Reservation.objects.create(
        resource=resource_with_opening_hours,
        begin=now,
        end=now + timedelta(hours=2),
        user=user,
        state=reservation_state,
        approved_at=now - approved_at if approved_at else None,
        requested_at=now - requested_at if requested_at else None,
    )

    order = OrderFactory(reservation=reservation, state=order_state)

    if order_created:
        OrderLogEntry.objects.create(
            order=order,
        )
        OrderLogEntry.objects.update(
            timestamp=now - order_created,
        )

    num_orders = 1 if expired else 0

    assert Order.objects.update_expired() == num_orders


def test_get_price_correct(order_with_products):
    """Test price calculation returns the correct combined sum for products

    Two hour reservation of two order lines with a price of 10, where one product
    has an hourly rate and one is with a fixed price, plus individual product
    tax of 24% should equal 37.20"""
    price = order_with_products.get_price()
    assert price == Decimal("37.20")


@pytest.mark.parametrize(
    "order_state, expected_reservation_state",
    (
        (Order.CONFIRMED, Reservation.CONFIRMED),
        (Order.REJECTED, Reservation.CANCELLED),
        (Order.EXPIRED, Reservation.CANCELLED),
        (Order.CANCELLED, Reservation.CANCELLED),
    ),
)
def test_set_state_sets_reservation_state(
    two_hour_reservation, order_state, expected_reservation_state
):
    old_order_state = (
        Order.CONFIRMED if order_state == Order.CANCELLED else Order.WAITING
    )
    order = OrderFactory(reservation=two_hour_reservation, state=old_order_state)

    order.set_state(order_state)

    two_hour_reservation.refresh_from_db()
    assert two_hour_reservation.state == expected_reservation_state


@pytest.mark.parametrize(
    "state, new_state",
    (
        (Order.REJECTED, Order.CONFIRMED),
        (Order.REJECTED, Order.EXPIRED),
        (Order.REJECTED, Order.CANCELLED),
        (Order.CONFIRMED, Order.REJECTED),
        (Order.CONFIRMED, Order.EXPIRED),
        (Order.EXPIRED, Order.REJECTED),
        (Order.EXPIRED, Order.CONFIRMED),
        (Order.EXPIRED, Order.CANCELLED),
        (Order.CANCELLED, Order.REJECTED),
        (Order.CANCELLED, Order.CONFIRMED),
        (Order.CANCELLED, Order.EXPIRED),
        (Order.WAITING, Order.CANCELLED),
    ),
)
def test_set_state_denied_transitions(two_hour_reservation, state, new_state):
    order = OrderFactory(reservation=two_hour_reservation, state=state)
    with pytest.raises(OrderStateTransitionError):
        order.set_state(new_state)


@pytest.mark.parametrize(
    "state, new_state",
    (
        (Order.WAITING, Order.CONFIRMED),
        (Order.WAITING, Order.EXPIRED),
        (Order.WAITING, Order.REJECTED),
        (Order.CONFIRMED, Order.CANCELLED),
    ),
)
def test_set_state_allowed_transitions(two_hour_reservation, state, new_state):
    order = OrderFactory(reservation=two_hour_reservation, state=state)
    order.set_state(new_state)
    assert order.state == new_state
