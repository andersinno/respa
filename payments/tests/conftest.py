import datetime
from decimal import Decimal

import factory.random
import pytest
from pytz import UTC

from payments.factories import OrderFactory, OrderLineFactory
from payments.models import Order, PRICE_FIXED, PRICE_PER_PERIOD
from resources.models import Reservation
from resources.tests.conftest import *  # noqa


@pytest.fixture(autouse=True)
def set_fixed_random_seed():
    factory.random.reseed_random(777)


@pytest.fixture()
def two_hour_reservation(resource_in_unit, user):
    """A two-hour reservation fixture with actual datetime objects"""
    return Reservation.objects.create(
        resource=resource_in_unit,
        begin=datetime.datetime(2119, 5, 5, 10, 0, 0, tzinfo=UTC),
        end=datetime.datetime(2119, 5, 5, 12, 0, 0, tzinfo=UTC),
        user=user,
        event_subject='some fancy event',
        host_name='esko',
        reserver_name='martta',
        state=Reservation.CONFIRMED,
        billing_first_name='Seppo',
        billing_last_name='Testi',
        billing_email_address='test@example.com',
        billing_address_street='Test street 1',
        billing_address_zip='12345',
        billing_address_city='Testcity',
    )


@pytest.fixture
def requested_reservation_with_order(resource_in_unit, user):
    begin = timezone.now() + datetime.timedelta(days=2)
    reservation = Reservation.objects.create(
        resource=resource_in_unit,
        begin=begin,
        end=begin + datetime.timedelta(hours=2),
        user=user,
        requested_at=timezone.now(),
    )
    order = OrderFactory.create(
        order_number='def456',
        state=Order.WAITING,
        reservation=reservation
    )
    OrderLineFactory.create(
        quantity=1,
        product__name="Test product",
        unit_price=Decimal('12.40'),
        tax_percentage=Decimal('24.00'),
        price_type=PRICE_PER_PERIOD,
        price_period=datetime.timedelta(hours=1),
        total_price=Decimal('24.80'),
        order=order
    )
    reservation.state=Reservation.REQUESTED
    reservation.save()
    return reservation


@pytest.fixture()
def order_with_products(two_hour_reservation):
    Reservation.objects.filter(id=two_hour_reservation.id).update(state=Reservation.WAITING_FOR_PAYMENT)
    two_hour_reservation.refresh_from_db()

    order = OrderFactory.create(
        order_number='abc123',
        state=Order.WAITING,
        reservation=two_hour_reservation
    )
    OrderLineFactory.create(
        quantity=1,
        product__name="Test product",
        unit_price=Decimal('12.40'),
        tax_percentage=Decimal('24.00'),
        price_type=PRICE_PER_PERIOD,
        price_period=datetime.timedelta(hours=1),
        total_price=Decimal('24.80'),
        order=order
    )
    OrderLineFactory.create(
        quantity=1,
        product__name="Test product 2",
        unit_price=Decimal('12.40'),
        tax_percentage=Decimal('24.00'),
        price_type=PRICE_FIXED,
        total_price=Decimal('12.40'),
        order=order
    )
    return order
