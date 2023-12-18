import datetime
import pytest
import requests
import uuid
from django.core.exceptions import ValidationError
from django.utils import timezone
from unittest import mock

from kulkunen.drivers.securitas import SecuritasDriver
from kulkunen.models import (
    AccessControlGrant,
    AccessControlResource,
    AccessControlSystem,
    AccessControlUser,
)
from resources.models import Reservation

MOCK_CODE = {
    "id": 12345,
    "code": 54321,
}

MOCK_ACCESS = {
    "resourceGroupAccessId": 33333,
}


class MockResponse:
    url: str
    status_code: int
    content: bytes = b""

    def __init__(self, url, status_code=200, json_data=None):
        self.url = url
        self.status_code = status_code
        self.json_data = json_data or {}

    def json(self):
        return self.json_data

    def raise_for_status(self):
        if self.status_code > 399:
            raise requests.HTTPError("error", response=self)


@pytest.fixture
def securitas_ac_system():
    return AccessControlSystem.objects.create(
        name="securitas",
        driver="securitas",
        driver_config={
            "api_key": uuid.uuid4().hex,
        },
    )


@pytest.fixture
def securitas_ac_resource(securitas_ac_system, resource_in_unit):
    return AccessControlResource.objects.create(
        system=securitas_ac_system,
        resource=resource_in_unit,
        driver_config={
            "group_id": "12345",
        },
    )


@pytest.fixture
def securitas_driver(securitas_ac_system):
    return SecuritasDriver(securitas_ac_system)


@pytest.fixture
def reservation(securitas_ac_resource, user):
    begin = timezone.now()
    end = begin + datetime.timedelta(hours=2)
    reservation = Reservation.objects.create(
        resource=securitas_ac_resource.resource,
        begin=begin,
        end=end,
        user=user,
    )
    return reservation


@pytest.mark.django_db()
def test_install_grant_not_installing(
    securitas_driver, securitas_ac_resource, reservation
):
    grant = AccessControlGrant.objects.create(
        state=AccessControlGrant.REQUESTED,
        resource=securitas_ac_resource,
        reservation=reservation,
        ends_at=reservation.end,
        starts_at=reservation.begin,
    )

    with pytest.raises(AssertionError):
        securitas_driver.install_grant(grant)


@pytest.mark.django_db()
def test_install_grant_new_user(securitas_driver, securitas_ac_resource, reservation):
    grant = AccessControlGrant.objects.create(
        state=AccessControlGrant.INSTALLING,
        resource=securitas_ac_resource,
        reservation=reservation,
        ends_at=reservation.end,
        starts_at=reservation.begin,
    )

    def _mock_post(url, *args, **kwargs):
        data = MOCK_CODE if url.endswith("/codes") else MOCK_ACCESS
        return MockResponse(url, json_data=data)

    with mock.patch("requests.post", _mock_post):
        securitas_driver.install_grant(grant)

    grant.refresh_from_db()

    assert grant.state == AccessControlGrant.INSTALLED
    assert grant.access_code == "54321"
    assert grant.identifier == "33333"
    assert grant.driver_data == {"code_id": 12345}
    assert grant.user.user == reservation.user
    assert grant.user.identifier == str(reservation.user.pk)


@pytest.mark.django_db()
def test_install_grant_missing_group_id(
    securitas_driver, securitas_ac_resource, reservation
):
    securitas_ac_resource.driver_config = {}
    securitas_ac_resource.save(update_fields=["driver_config"])

    grant = AccessControlGrant.objects.create(
        state=AccessControlGrant.INSTALLING,
        resource=securitas_ac_resource,
        reservation=reservation,
        ends_at=reservation.end,
        starts_at=reservation.begin,
    )

    def _mock_post(url, *args, **kwargs):
        data = MOCK_CODE if url.endswith("/codes") else MOCK_ACCESS
        return MockResponse(url, json_data=data)

    with mock.patch("requests.post", _mock_post):
        with pytest.raises(ValidationError):
            securitas_driver.install_grant(grant)

    grant.refresh_from_db()

    assert grant.state == AccessControlGrant.INSTALLING
    assert grant.access_code is None
    assert grant.identifier is None
    assert grant.driver_data is None
    assert grant.user is None


@pytest.mark.django_db()
def test_install_grant_no_pincode(securitas_driver, securitas_ac_resource, reservation):
    grant = AccessControlGrant.objects.create(
        state=AccessControlGrant.INSTALLING,
        resource=securitas_ac_resource,
        reservation=reservation,
        ends_at=reservation.end,
        starts_at=reservation.begin,
    )
    securitas_ac_resource.driver_config.update({"uses_pincode": False})
    securitas_ac_resource.save(update_fields=["driver_config"])

    with mock.patch(
        "requests.post", return_value=MockResponse("/access", json_data=MOCK_ACCESS)
    ):
        securitas_driver.install_grant(grant)

    grant.refresh_from_db()

    assert grant.state == AccessControlGrant.INSTALLED
    assert grant.access_code is None
    assert grant.driver_data is None
    assert grant.identifier == "33333"
    assert grant.user.user == reservation.user
    assert grant.user.identifier == str(reservation.user.pk)


@pytest.mark.django_db()
def test_install_grant_existing_user(
    securitas_driver, securitas_ac_resource, reservation
):
    grant = AccessControlGrant.objects.create(
        state=AccessControlGrant.INSTALLING,
        resource=securitas_ac_resource,
        reservation=reservation,
        ends_at=reservation.end,
        starts_at=reservation.begin,
        user=AccessControlUser.objects.create(
            user=reservation.user,
            identifier=str(reservation.user.pk),
            system=securitas_driver.system,
        ),
    )

    def _mock_post(url, *args, **kwargs):
        data = MOCK_CODE if url.endswith("/codes") else MOCK_ACCESS
        return MockResponse(url, json_data=data)

    with mock.patch("requests.post", _mock_post):
        securitas_driver.install_grant(grant)

    grant.refresh_from_db()

    assert grant.state == AccessControlGrant.INSTALLED
    assert grant.access_code == "54321"
    assert grant.identifier == "33333"
    assert grant.driver_data == {"code_id": 12345}
    assert grant.user.user == reservation.user
    assert grant.user.identifier == str(reservation.user.pk)


@pytest.mark.django_db()
def test_install_grant_bad_response(
    securitas_driver, securitas_ac_resource, reservation
):
    grant = AccessControlGrant.objects.create(
        state=AccessControlGrant.INSTALLING,
        resource=securitas_ac_resource,
        reservation=reservation,
        ends_at=reservation.end,
        starts_at=reservation.begin,
    )

    with mock.patch(
        "requests.post", return_value=MockResponse("/access", status_code=400)
    ):
        with pytest.raises(requests.RequestException):
            securitas_driver.install_grant(grant)

    grant.refresh_from_db()

    assert grant.state == AccessControlGrant.INSTALLING
    assert grant.user is None
    assert grant.access_code is None
    assert grant.identifier is None


@pytest.mark.django_db()
def test_remove_grant(securitas_driver, securitas_ac_resource, reservation):
    grant = AccessControlGrant.objects.create(
        state=AccessControlGrant.REMOVING,
        resource=securitas_ac_resource,
        reservation=reservation,
        ends_at=reservation.end,
        starts_at=reservation.begin,
        identifier="12345",
        driver_data={
            "code_id": 12345,
        },
    )

    def _mock_post(url, *args, **kwargs):
        return MockResponse(url)

    with mock.patch("requests.delete", _mock_post):
        securitas_driver.remove_grant(grant)

    grant.refresh_from_db()

    assert grant.state == AccessControlGrant.REMOVED
    assert grant.removed_at


@pytest.mark.django_db()
def test_remove_grant_no_pincode(securitas_driver, securitas_ac_resource, reservation):
    grant = AccessControlGrant.objects.create(
        state=AccessControlGrant.REMOVING,
        resource=securitas_ac_resource,
        reservation=reservation,
        ends_at=reservation.end,
        starts_at=reservation.begin,
        identifier="12345",
        driver_data=None,
    )

    def _mock_post(url, *args, **kwargs):
        return MockResponse(url)

    with mock.patch("requests.delete", _mock_post):
        securitas_driver.remove_grant(grant)

    grant.refresh_from_db()

    assert grant.state == AccessControlGrant.REMOVED


@pytest.mark.django_db()
def test_remove_grant_invalid_state(
    securitas_driver, securitas_ac_resource, reservation
):
    grant = AccessControlGrant.objects.create(
        state=AccessControlGrant.INSTALLED,
        resource=securitas_ac_resource,
        reservation=reservation,
        ends_at=reservation.end,
        starts_at=reservation.begin,
        identifier="12345",
        driver_data={
            "code_id": 12345,
        },
    )

    with pytest.raises(AssertionError):
        securitas_driver.remove_grant(grant)

    grant.refresh_from_db()

    assert grant.state == AccessControlGrant.INSTALLED


@pytest.mark.django_db()
def test_remove_grant_invalid_response(
    securitas_driver, securitas_ac_resource, reservation
):
    grant = AccessControlGrant.objects.create(
        state=AccessControlGrant.REMOVING,
        resource=securitas_ac_resource,
        reservation=reservation,
        ends_at=reservation.end,
        starts_at=reservation.begin,
        identifier="12345",
        driver_data={
            "code_id": 12345,
        },
    )

    with mock.patch(
        "requests.delete",
        return_value=MockResponse(
            "/access/12345",
            status_code=404,
        ),
    ):
        with pytest.raises(requests.RequestException):
            securitas_driver.remove_grant(grant)

    grant.refresh_from_db()

    assert grant.state == AccessControlGrant.REMOVING
