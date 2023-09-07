import datetime
from django.conf import settings
from django.template import loader
from django.utils import timezone
from django.utils.translation import gettext as _

from payments.utils import round_price
from resources.models import Reservation


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


def get_sales_order_items(reservation):
    cost_center_code = reservation.resource.unit.sap_cost_center_code

    for line in reservation.get_order().order_lines.all():
        yield {
            "currency": "EUR",
            "description": line.product.name,
            # always use "1" as SAP will calculate total price based on units
            "quantity": 1,
            "unit_price": round_price(line.total_price),
            "profit_center": cost_center_code,
            # dummy value
            "material": "1111",
            # before tax
            "price_condition": "ZYMH",
        }


def get_sales_orders(reservations):
    """Returns the sales order context data."""
    now = timezone.now()

    for reservation in reservations:
        address = {
            "street": reservation.company_address_street,
            "town": reservation.company_address_city,
            "postcode": reservation.company_address_zip,
        }

        if (
            reservation.begin
            and reservation.end
            and (reservation.end - reservation.begin) > datetime.timedelta(hours=24)
        ):
            billing_period = _("Invoice from %(begin)s to %(end)s") % {
                "begin": reservation.begin.strftime("%d.%m.%Y"),
                "end": reservation.end.strfime("%d.%m.%Y"),
            }
        elif reservation.begin:
            billing_period = _("Invoice for %(begin)s") % {
                "begin": reservation.begin.strftime("%d.%m.%Y"),
            }
        else:
            billing_period = ""

        yield {
            "reference": reservation.pk,
            "business_id": reservation.reserver_id,
            "company_name": reservation.company,
            "address": address,
            "billing_date": now,
            "billing_period": billing_period,
            "interface_id": settings.RESPA_SAP_INTERFACE_ID,
            # assumed defaults
            "distribution_channel": "00",
            "division": "00",
            "sales_order_type": "Z001",
            "items": get_sales_order_items(reservation),
        }


def generate_sales_order(reservations):
    """Generates XML document as a string containing all invoices.

    This document can be then sent to SAP for processing.

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
