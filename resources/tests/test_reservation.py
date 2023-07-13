import arrow
import datetime
import pytest
from datetime import timedelta

from guardian.shortcuts import assign_perm
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.translation import activate
from freezegun import freeze_time

from payments.factories import (
    OrderFactory,
    OrderWithOrderLinesFactory,
    OrderLineFactory,
)
from resources.enums import UnitAuthorizationLevel
from resources.models import (
    Day,
    Period,
    Reservation,
    ReservationMetadataSet,
    Resource,
    ResourceType,
    Unit,
    UnitAuthorization,
)


class ReservationTestCase(TestCase):
    def setUp(self):
        u1 = Unit.objects.create(
            name="Unit 1", id="unit_1", time_zone="Europe/Helsinki"
        )
        u2 = Unit.objects.create(
            name="Unit 2", id="unit_2", time_zone="Europe/Helsinki"
        )
        rt = ResourceType.objects.create(name="Type 1", id="type_1", main_type="space")
        Resource.objects.create(name="Resource 1a", id="r1a", unit=u1, type=rt)
        Resource.objects.create(name="Resource 1b", id="r1b", unit=u1, type=rt)
        Resource.objects.create(name="Resource 2a", id="r2a", unit=u2, type=rt)
        Resource.objects.create(name="Resource 2b", id="r2b", unit=u2, type=rt)

        p1 = Period.objects.create(
            start="2116-06-01", end="2116-09-01", unit=u1, name=""
        )
        p2 = Period.objects.create(
            start="2116-06-01", end="2116-09-01", unit=u2, name=""
        )
        p3 = Period.objects.create(
            start="2116-06-01", end="2116-09-01", resource_id="r1a", name=""
        )
        Day.objects.create(period=p1, weekday=0, opens="08:00", closes="22:00")
        Day.objects.create(period=p2, weekday=1, opens="08:00", closes="16:00")
        Day.objects.create(period=p3, weekday=0, opens="08:00", closes="18:00")

        u1.update_opening_hours()
        u2.update_opening_hours()

    def test_opening_hours(self):
        r1a = Resource.objects.get(id="r1a")
        r1b = Resource.objects.get(id="r1b")

        date = arrow.get("2116-06-01").date()
        end = arrow.get("2116-06-02").date()
        days = r1a.get_opening_hours(begin=date, end=end)  # Monday
        hours = days[date][0]  # first day object of chosen days
        self.assertEqual(hours["opens"].time(), datetime.time(8, 00))
        self.assertEqual(hours["closes"].time(), datetime.time(18, 00))

        days = r1b.get_opening_hours(begin=date, end=end)  # Monday
        hours = days[date][0]  # first day object of chosen days
        self.assertEqual(hours["opens"].time(), datetime.time(8, 00))
        self.assertEqual(hours["closes"].time(), datetime.time(22, 00))

    def test_reservation(self):
        r1a = Resource.objects.get(id="r1a")
        Resource.objects.get(id="r1b")

        tz = timezone.get_current_timezone()
        begin = tz.localize(datetime.datetime(2116, 6, 1, 8, 0, 0))
        end = begin + datetime.timedelta(hours=2)

        reservation = Reservation.objects.create(resource=r1a, begin=begin, end=end)
        reservation.clean()

        # Attempt overlapping reservation
        with self.assertRaises(ValidationError):
            reservation = Reservation(resource=r1a, begin=begin, end=end)
            reservation.clean()

        valid_begin = begin + datetime.timedelta(hours=3)
        valid_end = end + datetime.timedelta(hours=3)

        # Attempt incorrectly aligned begin time
        with self.assertRaises(ValidationError):
            reservation = Reservation(
                resource=r1a,
                begin=valid_begin + datetime.timedelta(minutes=1),
                end=valid_end,
            )
            reservation.clean()

        # Attempt incorrectly aligned end time
        with self.assertRaises(ValidationError):
            reservation = Reservation(
                resource=r1a,
                begin=valid_begin,
                end=valid_end + datetime.timedelta(minutes=1),
            )
            reservation.clean()

        # Attempt reservation that starts before the resource opens
        # Should not raise an exception as this check isn't included in model clean
        reservation = Reservation(
            resource=r1a, begin=begin - datetime.timedelta(hours=1), end=begin
        )
        reservation.clean()

        begin = tz.localize(datetime.datetime(2116, 6, 1, 16, 0, 0))
        end = begin + datetime.timedelta(hours=2)

        # Make a reservation that ends when the resource closes
        reservation = Reservation(resource=r1a, begin=begin, end=end)
        reservation.clean()

        # Attempt reservation that ends after the resource closes
        # Should not raise an exception as this check isn't included in model clean
        reservation = Reservation(
            resource=r1a, begin=begin, end=end + datetime.timedelta(hours=1)
        )
        reservation.clean()


@pytest.mark.parametrize(
    (
        "need_manual_confirmation",
        "need_manual_confirmation_for_zero_price",
        "is_free",
        "requires_confirmation",
    ),
    (
        (True, True, False, True),
        (True, True, True, True),
        (True, False, False, True),
        (True, False, True, True),
        (False, True, False, False),
        (False, True, True, True),
        (False, False, True, False),
        (False, False, False, False),
    ),
)
@pytest.mark.django_db
def test_need_reservation(
    space_resource_type,
    user,
    need_manual_confirmation,
    need_manual_confirmation_for_zero_price,
    is_free,
    requires_confirmation,
):
    resource = Resource.objects.create(
        name="resource",
        type=space_resource_type,
        need_manual_confirmation=need_manual_confirmation,
        need_manual_confirmation_for_zero_price=need_manual_confirmation_for_zero_price,
    )
    now = timezone.now()
    reservation = Reservation.objects.create(
        resource=resource,
        begin=now,
        user=user,
        end=now + datetime.timedelta(hours=2),
    )

    if is_free:
        order = OrderFactory(reservation=reservation)
        OrderLineFactory(order=order, unit_price=0, total_price=0)

    else:
        OrderWithOrderLinesFactory(reservation=reservation)

    assert reservation.need_manual_confirmation() is requires_confirmation


class TestPaymentLink:
    payment_link = "https://verkkomaksutesti.cpu.fi/kassa/order-pay/4751/?pay_for_order=true&key=wc_order_Fzy20q31ujVqd"  # noqa

    @pytest.fixture
    def reservation_times(self):
        begin = timezone.now() + timedelta(days=3)
        end = begin + timedelta(hours=1)
        return (begin, end)

    @pytest.mark.django_db
    def test_get_payment_link_resource_confirmed(
        self, resource_in_unit, reservation_times
    ):
        reservation = Reservation.objects.create(
            resource=resource_in_unit,
            begin=reservation_times[0],
            end=reservation_times[1],
            state=Reservation.CONFIRMED,
        )

        OrderFactory(reservation=reservation, payment_link=self.payment_link)

        reservation.refresh_from_db()

        assert reservation.get_payment_link() is None

    @pytest.mark.django_db
    def test_get_payment_link_resource_waiting_for_payment(
        self, resource_in_unit, reservation_times
    ):
        reservation = Reservation.objects.create(
            resource=resource_in_unit,
            begin=reservation_times[0],
            end=reservation_times[1],
            state=Reservation.WAITING_FOR_PAYMENT,
        )

        OrderFactory(reservation=reservation, payment_link=self.payment_link)

        reservation.refresh_from_db()

        assert reservation.get_payment_link() == self.payment_link

    @pytest.mark.django_db
    def test_get_payment_link_resource_waiting_for_payment_order_is_none(
        self, resource_in_unit, reservation_times
    ):
        reservation = Reservation.objects.create(
            resource=resource_in_unit,
            begin=reservation_times[0],
            end=reservation_times[1],
            state=Reservation.WAITING_FOR_PAYMENT,
        )

        assert reservation.get_payment_link() is None

    @pytest.mark.django_db
    def test_get_payment_link_resource_waiting_for_payment_link_is_empty(
        self, resource_in_unit, reservation_times
    ):
        reservation = Reservation.objects.create(
            resource=resource_in_unit,
            begin=reservation_times[0],
            end=reservation_times[1],
            state=Reservation.WAITING_FOR_PAYMENT,
        )

        OrderFactory(reservation=reservation),

        assert reservation.get_payment_link() is None


@pytest.mark.django_db
def test_need_manual_confirmation_metadata_set(resource_in_unit):
    data_set = ReservationMetadataSet.objects.get(name="default")
    assert data_set.supported_fields.exists()
    assert data_set.required_fields.exists()


@freeze_time("2115-04-02")
@pytest.mark.django_db
def test_valid_reservation_duration_with_slot_size(resource_with_opening_hours):
    resource_with_opening_hours.min_period = datetime.timedelta(hours=1)
    resource_with_opening_hours.slot_size = datetime.timedelta(minutes=30)
    resource_with_opening_hours.save()

    tz = timezone.get_current_timezone()
    begin = tz.localize(datetime.datetime(2115, 6, 1, 8, 0, 0))
    end = begin + datetime.timedelta(hours=2, minutes=30)

    reservation = Reservation(
        resource=resource_with_opening_hours, begin=begin, end=end
    )
    reservation.clean()


@freeze_time("2115-04-02")
@pytest.mark.django_db
def test_invalid_reservation_duration_with_slot_size(resource_with_opening_hours):
    activate("en")

    resource_with_opening_hours.min_period = datetime.timedelta(hours=1)
    resource_with_opening_hours.slot_size = datetime.timedelta(minutes=30)
    resource_with_opening_hours.save()

    tz = timezone.get_current_timezone()
    begin = tz.localize(datetime.datetime(2115, 6, 1, 8, 0, 0))
    end = begin + datetime.timedelta(hours=2, minutes=45)

    reservation = Reservation(
        resource=resource_with_opening_hours, begin=begin, end=end
    )

    with pytest.raises(ValidationError) as error:
        reservation.clean()
    assert error.value.code == "invalid_time_slot"


@freeze_time("2115-04-02")
@pytest.mark.django_db
def test_admin_may_bypass_min_period(resource_with_opening_hours, user):
    """
    Admin users should be able to bypass min_period,
    and their minimum reservation time should be limited by slot_size
    """
    activate("en")

    # min_period is bypassed respecting slot_size restriction
    resource_with_opening_hours.min_period = datetime.timedelta(hours=1)
    resource_with_opening_hours.slot_size = datetime.timedelta(minutes=30)
    resource_with_opening_hours.save()

    tz = timezone.get_current_timezone()
    begin = tz.localize(datetime.datetime(2115, 6, 1, 8, 0, 0))
    end = begin + datetime.timedelta(hours=0, minutes=30)

    UnitAuthorization.objects.create(
        subject=resource_with_opening_hours.unit,
        level=UnitAuthorizationLevel.admin,
        authorized=user,
    )

    reservation = Reservation(
        resource=resource_with_opening_hours, begin=begin, end=end, user=user
    )
    reservation.clean()

    # min_period is bypassed and slot_size restriction is violated
    resource_with_opening_hours.slot_size = datetime.timedelta(minutes=25)
    resource_with_opening_hours.save()

    with pytest.raises(ValidationError) as error:
        reservation.clean()
    assert error.value.code == "invalid_time_slot"


@freeze_time("2023-01-01T11:00:00+02:00")
@pytest.mark.django_db
def test_state_change_to_requested_sets_request_time(new_reservation, user):
    assert new_reservation.requested_at is None
    new_reservation.set_state(Reservation.REQUESTED, user)
    assert new_reservation.requested_at == parse_datetime("2023-01-01T11:00:00+02:00")


@freeze_time("2023-01-01T11:00:00+02:00")
@pytest.mark.django_db
def test_state_change_from_requested_to_confirmed_sets_approval_time(
    requested_reservation, user
):
    assert requested_reservation.state == Reservation.REQUESTED
    assert requested_reservation.approved_at is None
    requested_reservation.set_state(Reservation.CONFIRMED, user)
    assert requested_reservation.approver == user
    assert requested_reservation.approved_at == parse_datetime(
        "2023-01-01T11:00:00+02:00"
    )


@freeze_time("2023-01-01T11:00:00+02:00")
@pytest.mark.django_db
def test_state_change_from_requested_to_waiting_for_payment_sets_approval_time(
    requested_reservation, user
):
    assert requested_reservation.state == Reservation.REQUESTED
    assert requested_reservation.approved_at is None
    requested_reservation.set_state(Reservation.WAITING_FOR_PAYMENT, user)
    assert requested_reservation.approver == user
    assert requested_reservation.approved_at == parse_datetime(
        "2023-01-01T11:00:00+02:00"
    )


class TestIsAllowedSameState:
    def create_reservation(self, resource, user, state):
        begin = timezone.now()
        end = begin + datetime.timedelta(hours=2)
        reservation = Reservation.objects.create(
            resource=resource,
            begin=begin,
            end=end,
            user=user,
            state=state,
        )

        assign_perm("unit:can_approve_reservation", user, resource.unit)

        return reservation

    @pytest.mark.django_db
    def test_is_allowed_same_state(self, resource_in_unit, user):
        reservation = self.create_reservation(
            resource_in_unit, user, Reservation.REQUESTED
        )
        assert reservation.is_new_state_allowed(Reservation.REQUESTED, user)

    @pytest.mark.django_db
    def test_is_not_allowed_user_not_permitted(self, resource_in_unit, user, user2):
        reservation = self.create_reservation(
            resource_in_unit, user, Reservation.REQUESTED
        )
        assert not reservation.is_new_state_allowed(Reservation.CANCELLED, user2)

    @pytest.mark.django_db
    def test_is_allowed_cancelled_from_requested(self, resource_in_unit, user):
        reservation = self.create_reservation(
            resource_in_unit, user, Reservation.REQUESTED
        )
        assert reservation.is_new_state_allowed(Reservation.CANCELLED, user)

    @pytest.mark.django_db
    def test_is_allowed_denied_from_requested(self, resource_in_unit, user):
        reservation = self.create_reservation(
            resource_in_unit, user, Reservation.REQUESTED
        )
        assert reservation.is_new_state_allowed(Reservation.DENIED, user)

    @pytest.mark.django_db
    def test_is_allowed_confirmed_from_requested_if_no_order(
        self, resource_in_unit, user
    ):
        reservation = self.create_reservation(
            resource_in_unit, user, Reservation.REQUESTED
        )
        assert reservation.is_new_state_allowed(Reservation.CONFIRMED, user)

    @pytest.mark.django_db
    def test_is_not_allowed_confirmed_from_requested_if_order(
        self, resource_in_unit, user
    ):
        reservation = self.create_reservation(
            resource_in_unit, user, Reservation.REQUESTED
        )
        OrderFactory(reservation=reservation)
        assert not reservation.is_new_state_allowed(Reservation.CONFIRMED, user)

    @pytest.mark.django_db
    def test_is_not_allowed_waiting_for_payment_from_requested_if_no_order(
        self, resource_in_unit, user
    ):
        reservation = self.create_reservation(
            resource_in_unit, user, Reservation.REQUESTED
        )
        assert not reservation.is_new_state_allowed(
            Reservation.WAITING_FOR_PAYMENT, user
        )

    @pytest.mark.django_db
    def test_is_allowed_waiting_for_payment_from_requested_if_order(
        self, resource_in_unit, user
    ):
        reservation = self.create_reservation(
            resource_in_unit, user, Reservation.REQUESTED
        )
        OrderFactory(reservation=reservation)

        assert reservation.is_new_state_allowed(Reservation.WAITING_FOR_PAYMENT, user)

    @pytest.mark.django_db
    def test_is_allowed_cancelled_from_created(self, resource_in_unit, user):
        reservation = self.create_reservation(
            resource_in_unit, user, Reservation.CREATED
        )
        assert reservation.is_new_state_allowed(Reservation.CANCELLED, user)

    @pytest.mark.django_db
    def test_is_not_allowed_denied_from_created(self, resource_in_unit, user):
        reservation = self.create_reservation(
            resource_in_unit, user, Reservation.CREATED
        )
        assert not reservation.is_new_state_allowed(Reservation.DENIED, user)

    @pytest.mark.django_db
    def test_is_not_allowed_confirmed_from_created(self, resource_in_unit, user):
        reservation = self.create_reservation(
            resource_in_unit, user, Reservation.CREATED
        )
        assert not reservation.is_new_state_allowed(Reservation.CONFIRMED, user)

    @pytest.mark.django_db
    def test_is_not_allowed_waiting_for_payment_from_created(
        self, resource_in_unit, user
    ):
        reservation = self.create_reservation(
            resource_in_unit, user, Reservation.CREATED
        )
        assert not reservation.is_new_state_allowed(
            Reservation.WAITING_FOR_PAYMENT, user
        )
