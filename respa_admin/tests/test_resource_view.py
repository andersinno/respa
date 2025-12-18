import faker
import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.test.utils import override_settings
from django.urls import reverse
from django.utils.translation import activate, deactivate

from resources.enums import UnitAuthorizationLevel
from resources.models import UnitAuthorization
from resources.tests.utils import use_fallback_message_storage

from ..views.resources import ManageUserPermissionsView, SaveResourceView

_faker = faker.Faker()


@pytest.fixture
def staff_user():
    return get_user_model().objects.create(
        username=_faker.user_name(),
        first_name=_faker.name(),
        last_name=_faker.name(),
        email=_faker.email(),
        is_staff=True,
    )


@pytest.fixture
def admin_user_with_permissions(general_admin, resource_in_unit):
    UnitAuthorization.objects.create(
        subject=resource_in_unit.unit,
        authorized=general_admin,
        level=UnitAuthorizationLevel.ADMIN,
    )
    return general_admin


@pytest.mark.django_db
@override_settings(
    RESPA_ADMIN_ACCESSIBILITY_API_BASE_URL="http://api.com/",
    RESPA_ADMIN_ACCESSIBILITY_VISIBILITY=["test_space"],
    RESPA_ADMIN_ACCESSIBILITY_API_SECRET="foo",
    RESPA_ADMIN_ACCESSIBILITY_API_SYSTEM_ID="bar",
)
def test_accessibility_api_link_creation(rf, resource_in_unit, general_admin):
    url = reverse(
        "respa_admin:edit-resource", kwargs={"resource_id": resource_in_unit.pk}
    )
    request = rf.get(url)
    request.user = general_admin
    response = SaveResourceView.as_view()(request, resource_id=resource_in_unit.pk)
    accessibility_data_link = response.context_data.get("accessibility_data_link")
    assert accessibility_data_link is not None
    assert accessibility_data_link.startswith("http://api.com/")


@pytest.mark.django_db
def test_manage_user_permissions_get(
    rf, resource_in_unit, admin_user_with_permissions, staff_user
):
    request = rf.get("/")
    request.user = admin_user_with_permissions

    response = ManageUserPermissionsView.as_view()(request, user_id=staff_user.pk)
    assert response.status_code == 200


@pytest.mark.django_db
def test_manage_user_permissions_post_invalid(
    rf, resource_in_unit, admin_user_with_permissions, staff_user
):
    request = rf.post("/", {})
    request.user = admin_user_with_permissions

    use_fallback_message_storage(request)

    activate("en")
    ManageUserPermissionsView.as_view()(request, user_id=staff_user.pk, locale="en")
    messages = get_messages(request)
    error_messages = [message.message for message in messages if message.level_tag == 'error']
    assert error_messages == ["Failed to save. Please check the form for errors."]
    deactivate()

    assert not UnitAuthorization.objects.filter(
        subject=resource_in_unit.unit,
        authorized=staff_user,
        level=UnitAuthorizationLevel.ADMIN,
    ).exists()


@pytest.mark.django_db
def test_manage_user_permissions_post_valid(
    rf, resource_in_unit, admin_user_with_permissions, staff_user
):
    request = rf.post(
        "/",
        {
            "unit_authorizations-TOTAL_FORMS": 1,
            "unit_authorizations-INITIAL_FORMS": 0,
            "unit_authorizations-MAX_NUM_FORMS": 1000,
            "unit_authorizations-MIN_NUM_FORMS": 0,
            "unit_authorizations-0-subject": resource_in_unit.unit.pk,
            "unit_authorizations-0-level": "admin",
            "unit_authorizations-0-can_approve_reservation": True,
        },
    )
    request.user = admin_user_with_permissions

    use_fallback_message_storage(request)

    response = ManageUserPermissionsView.as_view()(request, user_id=staff_user.pk)
    assert response.url == reverse(
        "respa_admin:edit-user", kwargs={"user_id": staff_user.pk}
    )

    assert UnitAuthorization.objects.filter(
        subject=resource_in_unit.unit,
        authorized=staff_user,
        level=UnitAuthorizationLevel.ADMIN,
    ).exists()


@pytest.mark.django_db
def test_manage_user_permissions_post_no_permissions(
    rf, resource_in_unit, general_admin, staff_user
):
    """User should not be able to assign permissions if they don't have them."""
    request = rf.post(
        "/",
        {
            "unit_authorizations-TOTAL_FORMS": 1,
            "unit_authorizations-INITIAL_FORMS": 0,
            "unit_authorizations-MAX_NUM_FORMS": 1000,
            "unit_authorizations-MIN_NUM_FORMS": 0,
            "unit_authorizations-0-subject": resource_in_unit.unit.pk,
            "unit_authorizations-0-level": "admin",
            "unit_authorizations-0-can_approve_reservation": True,
        },
    )
    request.user = general_admin

    use_fallback_message_storage(request)

    response = ManageUserPermissionsView.as_view()(request, user_id=staff_user.pk)
    assert response.status_code == 200

    assert not UnitAuthorization.objects.filter(
        subject=resource_in_unit.unit,
        authorized=staff_user,
        level=UnitAuthorizationLevel.ADMIN,
    ).exists()
