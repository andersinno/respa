import datetime

import pytest
from django.test import RequestFactory
from django.urls import reverse, reverse_lazy
from django.utils import translation
from freezegun import freeze_time

from resources.models import (
    Equipment, EquipmentCategory, Purpose, ReservationMetadataSet, Resource, ResourceType, TermsOfUse
)

from ..forms import ResourceForm, get_period_formset

NEW_RESOURCE_URL = reverse_lazy("respa_admin:new-resource")


@pytest.mark.django_db
def test_period_formset_with_minimal_valid_data(valid_resource_form_data):
    request = RequestFactory().post(NEW_RESOURCE_URL, data=valid_resource_form_data)
    period_formset_with_days = get_period_formset(request)
    assert period_formset_with_days.is_valid()


@pytest.mark.django_db
def test_period_formset_with_invalid_period_data(valid_resource_form_data):
    data = valid_resource_form_data
    data.pop("periods-0-start")
    with translation.override("fi"):
        request = RequestFactory().post(NEW_RESOURCE_URL, data=data)
        period_formset_with_days = get_period_formset(request)
    assert period_formset_with_days.is_valid() is False
    assert period_formset_with_days.errors == [
        {
            "__all__": ["Aseta 'start' ja 'end'"],
            "start": ["Tämä kenttä vaaditaan."],
        }
    ]


@pytest.mark.django_db
def test_period_formset_with_invalid_days_data(valid_resource_form_data):
    data = valid_resource_form_data
    data.pop("days-periods-0-0-weekday")
    with translation.override("fi"):
        request = RequestFactory().post(NEW_RESOURCE_URL, data=data)
        period_formset_with_days = get_period_formset(request)
    assert period_formset_with_days.is_valid() is False
    assert period_formset_with_days.errors == [{"__all__": ["Tarkista aukioloajat."]}]
    assert period_formset_with_days.forms[0].days.errors == [
        {"weekday": ["Tämä kenttä vaaditaan."]}
    ]


@pytest.mark.django_db
def test_create_resource_with_invalid_data_returns_errors(
    admin_client, empty_resource_form_data
):
    data = empty_resource_form_data
    with translation.override("fi"):
        response = admin_client.post(NEW_RESOURCE_URL, data=data)
    assert response.context["form"].errors == {
        "access_code_type": ["Tämä kenttä vaaditaan."],
        "authentication": ["Tämä kenttä vaaditaan."],
        "equipment": ["Valitse oikea vaihtoehto.  ei ole vaihtoehtojen joukossa."],
        "min_period": ["Tämä kenttä vaaditaan."],
        "slot_size": ["Tämä kenttä vaaditaan."],
        "name_fi": ["Tämä kenttä vaaditaan."],
        "purposes": ["Valitse oikea vaihtoehto.  ei ole vaihtoehtojen joukossa."],
        "type": ["Tämä kenttä vaaditaan."],
        "unit": ["Tämä kenttä vaaditaan."],
        "price_type": ["Tämä kenttä vaaditaan."],
    }
    assert response.context["period_formset_with_days"].errors == [
        {"__all__": ["Tarkista aukioloajat."]}
    ]


@pytest.mark.django_db
def test_create_resource_with_invalid_external_reservation_url_data(
    admin_client, valid_resource_form_data
):
    data = valid_resource_form_data.copy()
    data["external_reservation_url"] = "not-an-url"
    with translation.override("fi"):
        response = admin_client.post(NEW_RESOURCE_URL, data=data)
    assert response.context["form"].errors == {
        "external_reservation_url": ["Syötä oikea URL-osoite."],
    }


@pytest.mark.django_db
def test_resource_creation_with_valid_data(admin_client, valid_resource_form_data):
    assert Resource.objects.count() == 0  # No resources in the db
    response = admin_client.post(
        NEW_RESOURCE_URL, data=valid_resource_form_data, follow=True
    )
    assert response.status_code == 200
    assert response.context["form"].errors == {}
    assert Resource.objects.count() == 1  # One new resource in db
    new_resource = Resource.objects.first()
    assert new_resource.periods.count() == 1
    assert new_resource.periods.first().days.count() == 1
    assert new_resource.periods.first().days.first().weekday == 1


@pytest.mark.django_db
def test_resource_delete_period(admin_client, valid_resource_form_data):
    assert Resource.objects.count() == 0  # No resources in the db
    response = admin_client.post(
        NEW_RESOURCE_URL, data=valid_resource_form_data, follow=True
    )
    assert response.status_code == 200
    assert response.context["form"].errors == {}
    assert Resource.objects.count() == 1  # One new resource in db
    new_resource = Resource.objects.first()
    assert new_resource.periods.count() == 1
    period = new_resource.periods.first()

    edit_data = {
        **valid_resource_form_data,
        "periods-INITIAL_FORMS": 1,
        "periods-0-id": period.pk,
        "periods-0-resource": new_resource.pk,
        "periods-0-DELETE": "on",
    }

    response = admin_client.post(
        reverse(
            "respa_admin:edit-resource",
            kwargs={
                "resource_id": new_resource.pk,
            },
        ),
        data=edit_data,
        follow=True,
    )

    assert response.status_code == 200
    assert response.context["form"].errors == {}
    new_resource.refresh_from_db()
    assert new_resource.periods.count() == 0


@freeze_time("2018-06-12")
@pytest.mark.django_db
def test_resource_creation_sets_opening_hours(admin_client, valid_resource_form_data):
    """
    valid_resource_form_data sets the opening hours starting from 2018-06-06 only for Tuesdays.
    Time is frozen to 2018-06-12 which is the first Tuesday after that to test opening hours.
    """
    data = valid_resource_form_data.copy()
    data["days-periods-0-0-closes"] = "14:00"
    admin_client.post(NEW_RESOURCE_URL, data=data, follow=True)
    new_resource = Resource.objects.first()
    opening_hours = new_resource.get_opening_hours()
    date = datetime.date.today()
    assert date in opening_hours
    closing_time = opening_hours[date][0]["closes"]
    assert (
        closing_time is not None
    ), "Closing time for today should be 14:00, instead it is None"
    assert closing_time.hour == 14
    assert closing_time.minute == 0


@pytest.mark.django_db(transaction=True)
def test_resource_creation_with_empty_hours(admin_client, valid_resource_form_data):
    resource_count = Resource.objects.count()
    data = valid_resource_form_data.copy()
    data["days-periods-0-0-opens"] = ""
    data["days-periods-0-0-closes"] = ""
    data["days-periods-0-0-closed"] = ""
    response = admin_client.post(NEW_RESOURCE_URL, data=data, follow=True)
    assert response.status_code == 200
    assert (
        Resource.objects.count() == resource_count
    ), "No new resource should be created with invalid data"


@pytest.mark.django_db
def test_resource_creation_missing_start_end(admin_client, valid_resource_form_data):
    resource_count = Resource.objects.count()
    data = {
        **valid_resource_form_data,
        "periods-0-name": "",
        "periods-0-start": "",
        "periods-0-end": "",
    }
    response = admin_client.post(NEW_RESOURCE_URL, data=data, follow=True)
    assert response.status_code == 200
    assert (
        Resource.objects.count() == resource_count
    ), "No new resource should be created with invalid data"


@pytest.mark.django_db
def test_resource_creation_with_empty_hours_on_closed_day(
    admin_client, valid_resource_form_data
):
    resource_count = Resource.objects.count()
    data = valid_resource_form_data.copy()
    data["days-periods-0-0-opens"] = ""
    data["days-periods-0-0-closes"] = ""
    data["days-periods-0-0-closed"] = "on"
    response = admin_client.post(NEW_RESOURCE_URL, data=data, follow=True)
    assert response.status_code == 200
    assert (
        Resource.objects.count() == resource_count + 1
    ), "Closed day should allow empty hours"


@pytest.mark.django_db
def test_editing_resource_via_form_view(admin_client, valid_resource_form_data):
    assert Resource.objects.all().exists() is False
    # Create a resource via the form view
    response = admin_client.post(
        NEW_RESOURCE_URL, data=valid_resource_form_data, follow=True
    )
    assert response.status_code == 200
    resource = Resource.objects.first()

    # Edit the resource
    valid_resource_form_data.update(
        {
            "name_fi": "Edited name",
        }
    )
    response = admin_client.post(
        reverse("respa_admin:edit-resource", kwargs={"resource_id": resource.id}),
        data=valid_resource_form_data,
        follow=True,
    )
    assert response.status_code == 200
    assert Resource.objects.count() == 1  # Still only 1 resource in db

    # Validate that the changes did happen
    edited_resource = Resource.objects.first()
    assert edited_resource.name_fi == "Edited name"
    assert resource.name_fi != edited_resource.name


@pytest.mark.django_db
def test_only_active_purposes_are_visible():
    active_purpose = Purpose.objects.create(name="Active Purpose", active=True)
    inactive_purpose = Purpose.objects.create(name="Inactive Purpose", active=False)

    form = ResourceForm()
    purposes_field = form.fields['purposes']

    assert list(purposes_field.queryset) == [active_purpose]
    assert inactive_purpose not in purposes_field.queryset


@pytest.mark.django_db
def test_only_active_terms_of_use_are_visible():
    active_generic_terms = TermsOfUse.objects.create(
        name="Active Generic Terms",
        terms_type=TermsOfUse.TERMS_TYPE_GENERIC,
        active=True)
    active_payment_terms = TermsOfUse.objects.create(
        name="Active Payment Terms",
        terms_type=TermsOfUse.TERMS_TYPE_PAYMENT,
        active=True)
    inactive_generic_terms = TermsOfUse.objects.create(
        name="Inactive Generic Terms",
        terms_type=TermsOfUse.TERMS_TYPE_GENERIC,
        active=False)
    inactive_payment_terms = TermsOfUse.objects.create(
        name="Inactive Payment Terms",
        terms_type=TermsOfUse.TERMS_TYPE_PAYMENT,
        active=False)

    form = ResourceForm()
    generic_terms_field = form.fields['generic_terms']
    payment_terms_field = form.fields['payment_terms']

    assert list(generic_terms_field.queryset) == [active_generic_terms]
    assert inactive_generic_terms not in generic_terms_field.queryset

    assert list(payment_terms_field.queryset) == [active_payment_terms]
    assert inactive_payment_terms not in payment_terms_field.queryset


@pytest.mark.django_db
def test_only_active_resource_types_are_visible():
    active_resource_type = ResourceType.objects.create(
        name="Active space",
        main_type="space",
        active=True)
    inactive_resource_type = ResourceType.objects.create(
        name="Inactive space",
        main_type="space",
        active=False)

    form = ResourceForm()
    resource_type_field = form.fields['type']

    assert list(resource_type_field.queryset) == [active_resource_type]
    assert inactive_resource_type not in resource_type_field.queryset


@pytest.mark.django_db
def test_only_reservation_metadata_sets_are_visible():
    default_data_set = ReservationMetadataSet.objects.get(name="default")
    default_data_set.active = False
    default_data_set.save()
    active_metadata_set = ReservationMetadataSet.objects.create(
        name="Active metadata set",
        active=True)
    inactive_metadata_set = ReservationMetadataSet.objects.create(
        name="Inactive metadata set",
        active=False)

    form = ResourceForm()
    metadata_set_field = form.fields['reservation_metadata_set']

    assert list(metadata_set_field.queryset) == [active_metadata_set]
    assert inactive_metadata_set not in metadata_set_field.queryset


@pytest.mark.django_db
def test_only_active_equipments_are_visible():
    category = EquipmentCategory.objects.create(
        id="category",
        name="Category"
    )
    active_equipment = Equipment.objects.create(
        name="Active equipment",
        category=category,
        active=True)
    inactive_equipment = Equipment.objects.create(
        name="Inactive equipment",
        category=category,
        active=False)

    form = ResourceForm()
    equipment_field = form.fields['equipment']

    assert list(equipment_field.queryset) == [active_equipment]
    assert inactive_equipment not in equipment_field.queryset
