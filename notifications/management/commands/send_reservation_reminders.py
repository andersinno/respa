import logging
from datetime import timedelta

from django.core.management import BaseCommand
from django.utils import timezone

from resources.models import Reservation

logger = logging.getLogger(__name__)


def send_reservation_reminder(reservation):
    reservation.send_reservation_mail(notification_type="reservation_reminder")
    reservation.reminder_sent = True
    reservation.save()


class Command(BaseCommand):
    help = "Send reservation reminders"

    def handle(self, *args, **options):
        """
        Send reservation reminders for reservations that start in the next 24 hours.
        """

        reservations = Reservation.objects.filter(
            begin__gte=timezone.now(),
            begin__lte=timezone.now() + timedelta(days=1),
            state=Reservation.CONFIRMED,
            reminder_sent=False,
        )

        logger.info(f"Sending reminders for {reservations.count()} reservations")

        for reservation in reservations:
            send_reservation_reminder(reservation)
