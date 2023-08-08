import pytest
from datetime import timedelta
from decimal import Decimal
from django.utils import timezone

from payments.factories import OrderFactory, OrderLineFactory
from payments.models import Order
from payments.sap_invoices import (
    generate_sales_order,
    get_reservations_for_invoicing,
    get_sales_orders,
)
from resources.models import Reservation


@pytest.fixture()
def invoice_reservation(resource_with_opening_hours, user):
    now = timezone.now()
    reservation = Reservation.objects.create(
        resource=resource_with_opening_hours,
        begin=now,
        end=now + timedelta(hours=2),
        user=user,
        state=Reservation.CONFIRMED,
        invoice_requested=True,
        invoice_requested_at=now,
        invoice_approved_at=now,
        invoice_generated_at=None,
        reserver_id="Y-12456",
        company="test",
        company_address_street="123 Pihlajakatu",
        company_address_city="Helsinki",
        company_address_zip="11000",
    )

    order = OrderFactory(reservation=reservation, state=Order.CONFIRMED)
    OrderLineFactory(order=order)
    return reservation


@pytest.mark.django_db()
def test_get_reservations_for_invoicing(invoice_reservation):
    assert get_reservations_for_invoicing().count() == 1


@pytest.mark.django_db()
def test_get_reservations_for_invoicing_not_approved(invoice_reservation):
    Reservation.objects.update(invoice_approved_at=None)
    assert get_reservations_for_invoicing().count() == 0


@pytest.mark.django_db()
def test_get_reservations_for_invoicing_already_generated(invoice_reservation):
    Reservation.objects.update(invoice_generated_at=timezone.now())
    assert get_reservations_for_invoicing().count() == 0


@pytest.mark.django_db()
def test_get_sales_orders(invoice_reservation):
    sales_orders = list(get_sales_orders([invoice_reservation]))
    order = sales_orders[0]
    assert order["business_id"] == invoice_reservation.reserver_id
    assert order["address"]["town"] == invoice_reservation.company_address_city

    items = list(order["items"])
    assert len(items) == 1
    item = items[0]
    assert item["quantity"] == 1
    assert item["unit_price"] == Decimal("100.00")


@pytest.mark.django_db()
def test_generate_sales_order(invoice_reservation):
    xml_str = generate_sales_order(get_reservations_for_invoicing())
    assert "<BusinessID>Y-12456" in xml_str
    assert "<UnitPrice>100.00" in xml_str
    assert "<Town>Helsinki" in xml_str


@pytest.mark.django_db()
def test_generate_sales_order_if_empty():
    assert generate_sales_order(get_reservations_for_invoicing()) is None
