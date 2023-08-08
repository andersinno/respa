import pathlib
from django.core.management.base import BaseCommand
from django.template import loader
from django.utils import timezone
from django.utils.translation import gettext as _

from payments.sap_invoices import generate_sales_order, get_reservations_for_invoicing


class Command(BaseCommand):
    help = "Generates SAP XML Sales Order documents."

    def add_arguments(self, parser):
        parser.add_argument("--target_dir", help="Target directory")
        parser.add_argument(
            "--stdout",
            help="Write to STDOUT",
            action="store_true",
            default=False,
        )

    def handle(self, *args, **options):
        """Should generate SAP XML documents for all reservations where an
        invoice has been requested and approved.

        Documents are written to the target directory, using timestamped folders.

        TBD: provide optional URL for (s)ftp transfer instead of writing to dir.
        """
        reservations = get_reservations_for_invoicing()
        sales_order_xml = generate_sales_order(reservations)

        if sales_order_xml:
            now = timezone.now()
            # mark reservations invoices as done
            reservations.update(invoice_generated_at=now)

            if options["target_dir"]:
                filename = now.strftime("%d-%m-%Y-%H-%M.xml")
                target_dir = pathlib.Path(options["target_dir"])
                target_dir.mkdir(exist_ok=True, parents=True)

                with open(target_dir / filename, "w") as fp:
                    fp.write(sales_order_xml)

            if options["stdout"]:
                self.stdout.write(sales_order_xml)
