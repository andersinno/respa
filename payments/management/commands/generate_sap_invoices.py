from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from payments.models import Invoice
from payments.sap_invoices import generate_sales_order, get_reservations_for_invoicing


class Command(BaseCommand):
    help = "Generates SAP XML content for invoices."

    def add_arguments(self, parser):
        parser.add_argument(
            "--stdout",
            help="Write to STDOUT",
            action="store_true",
            default=False,
        )

    def handle(self, *args, **options):
        """Should generate SAP XML for all reservations where an invoice
        has been requested and approved. The XML content is saved to a
        related Invoice object.
        """
        reservations = get_reservations_for_invoicing()
        sales_order_xml = generate_sales_order(reservations)

        if sales_order_xml:
            now = timezone.now()
            with transaction.atomic():
                invoice = Invoice.objects.create(
                    xml=sales_order_xml,
                    xml_generated_at=now,
                )
                orders = [res.order for res in reservations]
                invoice.orders.set(orders)

                # mark reservations invoices as done
                reservations.update(invoice_generated_at=now)

            if options["stdout"]:
                self.stdout.write(sales_order_xml)
