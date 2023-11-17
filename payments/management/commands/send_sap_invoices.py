import paramiko

from django.core.management.base import BaseCommand
from django.conf import settings
from django.utils import timezone

from payments.models import Invoice

SFTP_SERVER_IP = settings.RESPA_INVOICES_SFTP_SERVER_IP
SFTP_USERNAME = settings.RESPA_INVOICES_SFTP_USERNAME
RSA_KEY_PATH = settings.RESPA_INVOICES_SFTP_RSA_KEY_PATH
RSA_KEY_PASSWORD = settings.RESPA_INVOICES_SFTP_RSA_KEY_PASSWORD


class Command(BaseCommand):
    help = "Sends the SAP invoices as XML files to an SFTP server."

    def add_arguments(self, parser):
        parser.add_argument(
            "--path", type=str, help="File path on the SFTP server", default="/out/"
        )

    def handle(self, *args, **options):
        invoices = Invoice.objects.filter(
            xml_generated_at__isnull=False, sent_to_sap_at__isnull=True
        )

        self.upload_xml_to_sftp(invoices, options.get("path"))

    def upload_xml_to_sftp(self, invoices, remote_path="/out/"):
        """
        Establishes a connection to the SFTP server and
        uploads the SAP invoices there as XML files.

        :param invoices The invoices to send to SAP
        :type invoices Queryset/List of Invoice objects
        """

        # Establish an SFTP connection
        self.stdout.write("Establishing connection to SFTP server...")

        pkey = paramiko.RSAKey.from_private_key_file(
            RSA_KEY_PATH, password=RSA_KEY_PASSWORD
        )
        ssh_client = paramiko.SSHClient()
        ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh_client.connect(
            SFTP_SERVER_IP, username=SFTP_USERNAME, pkey=pkey, look_for_keys=False
        )
        sftp = ssh_client.open_sftp()

        self.stdout.write("SFTP Connection established.")

        for invoice in invoices:
            # Prepare XML content and filename
            xml_content = invoice.xml.strip()
            timestamp = timezone.now().strftime("%Y%m%d%H%M%S")
            filename = f"{timestamp}_invoice_{invoice.id}.xml"

            self.stdout.write(f"Uploading invoice {invoice.id}")
            # Upload the XML content to the SFTP server
            with sftp.file(remote_path + filename, "w") as remote_file:
                remote_file.write(xml_content)

            self.stdout.write(f"Invoice with ID {invoice.id} uploaded to SFTP server")
            invoice.sent_to_sap_at = timezone.now()
            invoice.save()

        # Close the SFTP connection
        sftp.close()
        self.stdout.write("Connection to SFTP server closed.")
