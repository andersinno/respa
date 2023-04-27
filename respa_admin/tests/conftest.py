import pytest
from munigeo.models import Municipality

from resources.tests.conftest import (
    equipment,
    equipment_category,
    general_admin,
    generic_terms,
    payment_terms,
    purpose,
    resource_in_unit,
    resource_in_unit2,
    space_resource_type,
    test_unit,
    test_unit2,
)
from respa_pricing.tests.conftest import (
    event_type,
    price_list,
    resource,
    resource_type,
    user_group,
    price_list_with_product,
)

__all__ = [
    "empty_period_form_data",
    "empty_resource_form_data",
    "empty_unit_form_data",
    "equipment",
    "equipment_category",
    "event_type",
    "general_admin",
    "generic_terms",
    "municipality",
    "payment_terms",
    "price_list",
    "price_list_with_product",
    "purpose",
    "resource",
    "resource_in_unit",
    "resource_in_unit2",
    "resource_type",
    "space_resource_type",
    "test_unit",
    "test_unit2",
    "test_unit_form_data",
    "user_group",
    "valid_resource_form_data",
]

EMPTY_PRICE_LIST_FORM_DATA = {
    "name": "",
    "resource": "",
    "usergroup_prices-TOTAL_FORMS": "1",
    "usergroup_prices-INITIAL_FORMS": "0",
    "usergroup_prices-MIN_NUM_FORMS": "1",
    "usergroup_prices-MAX_NUM_FORMS": "1000",
    "usergroup_prices-0-id": "",
    "usergroup_prices-0-user_group": "",
    "usergroup_prices-0-price": "",
    "usergroup_prices-0-price_period": "01:00:00",
    "usergroup_prices-0-price_type": "per_period",
    "event_prices-TOTAL_FORMS": "0",
    "event_prices-INITIAL_FORMS": "0",
    "event_prices-MIN_NUM_FORMS": "0",
    "event_prices-MAX_NUM_FORMS": "1000",
}

EMPTY_RESOURCE_FORM_DATA = {
    "images-TOTAL_FORMS": ["1"],
    "images-INITIAL_FORMS": ["0"],
    "images-MIN_NUM_FORMS": ["0"],
    "images-MAX_NUM_FORMS": ["1000"],
    "periods-TOTAL_FORMS": ["1"],
    "periods-INITIAL_FORMS": ["0"],
    "periods-MIN_NUM_FORMS": ["0"],
    "periods-MAX_NUM_FORMS": ["1000"],
    "accessibility_summaries-TOTAL_FORMS": ["0"],
    "accessibility_summaries-INITIAL_FORMS": ["0"],
    "accessibility_summaries-MIN_NUM_FORMS": ["0"],
    "accessibility_summaries-MAX_NUM_FORMS": ["1000"],
    "unit": "",
    "type": "",
    "name": "",
    "description": "",
    "external_reservation_url": "",
    "purposes": "",
    "equipment": "",
    "responsible_contact_info": "",
    "people_capacity": "",
    "area": "",
    "min_period": "",
    "max_period": "",
    "reservable_max_days_in_advance": "",
    "max_reservations_per_user": "",
    "reservable": "",
    "reservation_info": "",
    "need_manual_confirmation": "",
    "authentication": "",
    "access_code_type": "",
    "max_price": "",
    "min_price": "",
    "price_type": "",
    "generic_terms": "",
    "payment_terms": "",
    "specific_terms": "",
    "reservation_confirmed_notification_extra": "",
    "images-0-caption": "",
    "images-0-type": "",
    "images-0-id": "",
    "images-0-resource": "",
    "periods-0-name": "",
    "periods-0-start": "",
    "periods-0-end": "",
    "periods-0-id": "",
    "periods-0-resource": "",
    "days-periods-0-TOTAL_FORMS": ["1"],
    "days-periods-0-INITIAL_FORMS": ["0"],
    "days-periods-0-MIN_NUM_FORMS": ["0"],
    "days-periods-0-MAX_NUM_FORMS": ["7"],
    "days-periods-0-0-weekday": "",
    "days-periods-0-0-opens": "",
    "days-periods-0-0-closes": "",
    "days-periods-0-0-closed": "",
    "days-periods-0-0-id": "",
    "days-periods-0-0-period": "",
}


EMPTY_UNIT_FORM_DATA = {
    "address_zip": "",
    "description": "",
    "name": "",
    "phone": "",
    "street_address": "",
    "www_url": "",
}


EMPTY_PERIOD_FORM_DATA = {
    "periods-TOTAL_FORMS": ["0"],
    "periods-INITIAL_FORMS": ["0"],
    "periods-MIN_NUM_FORMS": ["0"],
    "periods-MAX_NUM_FORMS": ["1000"],
    "periods-0-name": "",
    "periods-0-start": "",
    "periods-0-end": "",
    "periods-0-id": "",
    "periods-0-resource": "",
    "days-periods-0-TOTAL_FORMS": ["0"],
    "days-periods-0-INITIAL_FORMS": ["0"],
    "days-periods-0-MIN_NUM_FORMS": ["0"],
    "days-periods-0-MAX_NUM_FORMS": ["7"],
    "days-periods-0-0-weekday": "",
    "days-periods-0-0-opens": "",
    "days-periods-0-0-closes": "",
    "days-periods-0-0-closed": "",
    "days-periods-0-0-id": "",
    "days-periods-0-0-period": "",
}


@pytest.fixture
def empty_resource_form_data():
    return EMPTY_RESOURCE_FORM_DATA.copy()


@pytest.fixture
def empty_unit_form_data():
    return EMPTY_UNIT_FORM_DATA.copy()


@pytest.fixture
def empty_period_form_data():
    return EMPTY_PERIOD_FORM_DATA.copy()


@pytest.fixture
def empty_price_list_form_data():
    return EMPTY_PRICE_LIST_FORM_DATA.copy()


@pytest.fixture
def valid_price_list_form_data(empty_price_list_form_data, user_group):
    # TBD: add event type fields
    data = empty_price_list_form_data.copy()
    data.update(
        {
            "name": "test name",
            "usergroup_prices-0-id": "",
            "usergroup_prices-0-user_group": user_group.pk,
            "usergroup_prices-0-price": "100.00",
            "usergroup_prices-0-price_period": "01:00:00",
            "usergroup_prices-0-price_type": "per_period",
        }
    )
    return data


@pytest.fixture
def valid_resource_form_data(
    equipment,
    generic_terms,
    payment_terms,
    purpose,
    space_resource_type,
    test_unit,
    empty_resource_form_data,
):
    data = empty_resource_form_data
    data.update(
        {
            "access_code_type": "pin6",
            "authentication": "weak",
            "equipment": equipment.pk,
            "external_reservation_url": "http://calendar.example.tld",
            "generic_terms": generic_terms.pk,
            "payment_terms": payment_terms.pk,
            "max_period": "02:00:00",
            "min_period": "01:00:00",
            "slot_size": "00:30:00",
            "name_fi": "Test resource",
            "purposes": purpose.pk,
            "type": space_resource_type.pk,
            "unit": test_unit.pk,
            "periods-0-name": "Kesäkausi",
            "periods-0-start": "2018-06-06",
            "periods-0-end": "2018-08-01",
            "days-periods-0-0-opens": "08:00",
            "days-periods-0-0-closes": "12:00",
            "days-periods-0-0-weekday": "1",
            "price_type": "hourly",
        }
    )
    return data


@pytest.fixture
def test_unit_form_data(
    test_unit, empty_unit_form_data, empty_period_form_data, municipality
):
    empty_unit_form_data.update(
        {
            "address_zip": test_unit.address_zip or "",
            "description": test_unit.description or "",
            "municipality": municipality.pk,
            "name": test_unit.name or "",
            "phone": test_unit.phone or "",
            "street_address": test_unit.street_address or "",
            "www_url": test_unit.www_url or "",
            "cost_center_code": test_unit.cost_center_code or "",
        }
    )
    empty_unit_form_data.update(empty_period_form_data)
    return empty_unit_form_data


@pytest.fixture
def municipality():
    return Municipality.objects.create(id="test_municipality", name="Test Municipality")
