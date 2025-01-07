from datetime import timedelta
from unittest import mock

import pytest
from django.core.management import call_command
from django.utils import timezone

from resources.models import Reservation, Resource, ResourceType, Unit


@pytest.fixture
def reservation():
    resource_type = ResourceType.objects.get_or_create(main_type="space", name="space")[0]
    unit = Unit.objects.create(name="Test unit")
    resource = Resource.objects.create(
        name="Test resource",
        type=resource_type,
        unit=unit,
    )
    reservation = Reservation.objects.create(
        resource=resource,
        begin=timezone.now() + timedelta(hours=23),
        end=timezone.now() + timedelta(hours=24),
        reminder_sent=False,
    )
    return reservation


@pytest.mark.django_db
def test_send_reservation_reminder(reservation):
    """
    Test that the reminder is sent and the reminder_sent field is updated.
    """
    with mock.patch(
        "resources.models.Reservation.send_reservation_mail"
    ) as mock_send_mail:
        call_command("send_reservation_reminders")
        reservation.refresh_from_db()
        assert reservation.reminder_sent is True
        mock_send_mail.assert_called_once_with(notification_type="reservation_reminder")


@pytest.mark.django_db
def test_no_reminder_if_already_sent(reservation):
    """
    Test that the reminder is not sent if it has already been sent.
    """
    reservation.reminder_sent = True
    reservation.save()
    with mock.patch(
        "resources.models.Reservation.send_reservation_mail"
    ) as mock_send_mail:
        call_command("send_reservation_reminders")
        mock_send_mail.assert_not_called()


@pytest.mark.django_db
def test_no_reminder_for_reservation_not_within_24_hours(reservation):
    """
    Test that the reminder is not sent if the reservation is not in the next 24 hours.
    """
    reservation.begin = timezone.now() + timedelta(days=2)
    reservation.end = timezone.now() + timedelta(days=2, hours=1)
    reservation.save()
    with mock.patch(
        "notifications.management.commands.send_reservation_reminders.send_reservation_reminder"
    ) as mock_send_reminder:
        call_command("send_reservation_reminders")
        mock_send_reminder.assert_not_called()
