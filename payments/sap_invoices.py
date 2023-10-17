from django.conf import settings
from django.template import loader
from django.utils.translation import gettext as _

from resources.models import Reservation

from .models import SAPMaterialCode


def get_reservations_for_invoicing():
    """Returns reservations that are eligible for invoice generation.

    This should include all CONFIRMED reservations marked invoice approved.
    """
    return (
        Reservation.objects.filter(
            state=Reservation.CONFIRMED,
            order__isnull=False,
            invoice_requested=True,
            invoice_approved_at__isnull=False,
            invoice_generated_at__isnull=True,
        )
        .select_related(
            "resource",
            "resource__unit",
            "order",
        )
        .prefetch_related(
            "order__order_lines",
            "order__order_lines__product",
        )
        .order_by("invoice_approved_at")
    )


def get_sap_material_code(order_line):
    reservation = order_line.order.reservation
    unit = reservation.resource.unit
    income_account = unit.sap_income_account

    return SAPMaterialCode.objects.get(
        tax_percentage=order_line.tax_percentage, sap_income_account=income_account
    ).material_code


def get_sales_order_items(reservation):
    unit = reservation.resource.unit

    for line in reservation.get_order().order_lines.all():
        yield {
            "currency": "EUR",
            "description": reservation.resource.name,
            # always use "1" as SAP will calculate total price based on units
            "quantity": 1,
            "unit_price": line.get_pretax_price(),
            "profit_center": unit.sap_cost_center_code,
            "material": get_sap_material_code(line),
            "price_condition": "ZMYH",  # before tax
            "plant_id": unit.sap_unit_id,
        }


def get_sales_orders(reservations):
    """Returns the sales order context data."""

    for reservation in reservations:
        unit = reservation.resource.unit
        address = {
            "street": reservation.company_address_street,
            "town": reservation.company_address_city,
            "postcode": reservation.company_address_zip,
        }

        if reservation.begin and reservation.end:
            billing_period = _("Invoice from %(begin)s to %(end)s") % {
                "begin": reservation.begin.strftime("%d.%m.%Y %H:%M"),
                "end": reservation.end.strftime("%d.%m.%Y %H:%M"),
            }
        else:
            billing_period = ""

        yield {
            "reference": reservation.pk,
            "business_id": reservation.reserver_id,
            "company_name": reservation.company,
            "address": address,
            "billing_period": billing_period,
            "interface_id": settings.RESPA_SAP_INTERFACE_ID,
            # assumed defaults
            "distribution_channel": "00",
            "division": "00",
            "sales_organization": unit.sap_sales_organization,
            "sales_order_type": "ZVRV",  # TODO: Use "ZVSV" for internal reservations
            "items": get_sales_order_items(reservation),
        }


def generate_sales_order(reservations):
    """Generates the XML as a string containing all invoices.

    This XML can be then sent to SAP for processing.

    If no available invoiceable reservations, returns `None`.
    """

    return (
        loader.render_to_string(
            "payments/sap/sales_order.xml",
            {
                "orders": get_sales_orders(reservations),
            },
        )
        if reservations.exists()
        else None
    )
