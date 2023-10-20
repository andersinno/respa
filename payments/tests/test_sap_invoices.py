import pytest
from datetime import timedelta
from decimal import Decimal
from django.utils import timezone

from payments.factories import OrderFactory, OrderLineFactory
from payments.models import Order, SAPIncomeAccount, SAPMaterialCode
from payments.sap_invoices import (
    generate_sales_order,
    get_reservations_for_invoicing,
    get_sales_orders,
    get_sap_material_code,
)
from resources.models import Reservation


@pytest.mark.django_db
@pytest.fixture
def income_account():
    return SAPIncomeAccount.objects.create(identifier="ACC123")


@pytest.mark.django_db
@pytest.fixture
def sap_material_code(income_account):
    return SAPMaterialCode.objects.create(
        sap_income_account=income_account,
        tax_percentage=Decimal("10.00"),
        material_code="MATERIAL123",
    )


@pytest.fixture()
def invoice_reservation(
    resource_with_opening_hours, income_account, sap_material_code, user
):
    now = timezone.now()
    resource_with_opening_hours.unit.sap_income_account = income_account
    resource_with_opening_hours.unit.save()
    reservation = Reservation.objects.create(
        resource=resource_with_opening_hours,
        begin=now - timedelta(hours=3),
        end=now - timedelta(hours=2),
        user=user,
        state=Reservation.CONFIRMED,
        invoice_requested=True,
        invoice_requested_at=now,
        invoice_approved_at=now,
        invoice_generated_at=None,
        invoice_marked_ready_at=now,
        reserver_id="Y-12456",
        company="test",
        company_address_street="123 Pihlajakatu",
        company_address_city="Helsinki",
        company_address_zip="11000",
    )

    order = OrderFactory(reservation=reservation, state=Order.CONFIRMED)
    OrderLineFactory(order=order, tax_percentage=Decimal("10.00"))
    return reservation


@pytest.mark.django_db()
def test_get_reservations_for_invoicing(invoice_reservation):
    assert get_reservations_for_invoicing().count() == 1


@pytest.mark.django_db()
def test_get_reservations_for_invoicing_not_approved(invoice_reservation):
    Reservation.objects.update(invoice_approved_at=None)
    assert get_reservations_for_invoicing().count() == 0


@pytest.mark.django_db()
def test_get_reservations_for_invoicing_not_marked_ready(invoice_reservation):
    Reservation.objects.update(invoice_marked_ready_at=None)
    assert get_reservations_for_invoicing().count() == 0


@pytest.mark.django_db()
def test_get_reservations_for_invoicing_not_in_the_past(invoice_reservation):
    Reservation.objects.update(end=timezone.now() + timedelta(hours=2))
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
    assert item["unit_price"] == Decimal("90.91")  # pre-tax


@pytest.mark.django_db()
def test_generate_sales_order(invoice_reservation):
    xml_str = generate_sales_order(get_reservations_for_invoicing())
    assert "<BusinessID>Y-12456" in xml_str
    assert "<UnitPrice>90.91" in xml_str
    assert "<Town>Helsinki" in xml_str
    assert "<ProfitCenter>CC123" in xml_str
    assert "<SalesOrganisation>O123" in xml_str
    assert "<Plant>U123" in xml_str


@pytest.mark.django_db()
def test_get_sap_material_code(invoice_reservation):
    order_line = invoice_reservation.order.order_lines.first()
    sap_material_code = get_sap_material_code(order_line)
    assert sap_material_code == "MATERIAL123"


@pytest.mark.django_db()
def test_generate_sales_order_if_empty():
    assert generate_sales_order(get_reservations_for_invoicing()) is None
