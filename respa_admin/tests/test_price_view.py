import pytest
from django.urls import reverse
from django.utils import translation

from resources.tests.utils import use_fallback_message_storage
from respa_pricing.models import PriceList, UserGroupPriceListItem

from ..views.prices import PriceListCopyView, PriceListCreateView, PriceListEditView


@pytest.mark.django_db
def test_price_list_create_get(user_group, event_type, general_admin, rf):
    request = rf.get("/")
    request.user = general_admin
    with translation.override("fi"):
        response = PriceListCreateView.as_view()(request)
        response.render()

    assert response.status_code == 200

    content = str(response.content)
    assert user_group.name in content
    assert event_type.name in content


@pytest.mark.django_db
def test_price_list_create_invalid_post(empty_price_list_form_data, general_admin, rf):
    request = rf.post("/", empty_price_list_form_data)
    request.user = general_admin
    with translation.override("fi"):
        response = PriceListCreateView.as_view()(request)

    assert response.status_code == 200
    assert response.context_data["form"].errors


@pytest.mark.django_db
def test_price_list_create_valid_post(valid_price_list_form_data, general_admin, rf):
    request = rf.post("/", valid_price_list_form_data)
    request.user = general_admin

    use_fallback_message_storage(request)

    with translation.override("fi"):
        response = PriceListCreateView.as_view()(request)

    new_price_list = PriceList.objects.get()
    assert new_price_list.name == valid_price_list_form_data["name"]

    assert response.url == reverse(
        "respa_admin:edit-price-list",
        kwargs={
            "price_list_id": new_price_list.pk,
        },
    )


@pytest.mark.django_db
def test_price_list_edit_get(price_list_with_product, general_admin, rf):
    request = rf.get("/")
    request.user = general_admin
    with translation.override("fi"):
        response = PriceListEditView.as_view()(
            request, price_list_id=price_list_with_product.pk
        )
        response.render()

    content = str(response.content)
    assert price_list_with_product.name in content


@pytest.mark.django_db
def test_price_list_edit_invalid_post(
    price_list_with_product, empty_price_list_form_data, general_admin, rf
):
    request = rf.post("/", empty_price_list_form_data)
    request.user = general_admin
    with translation.override("fi"):
        response = PriceListEditView.as_view()(
            request, price_list_id=price_list_with_product.pk
        )

    assert response.status_code == 200
    assert response.context_data["form"].errors


@pytest.mark.django_db
def test_price_list_edit_valid_post(
    price_list_with_product, valid_price_list_form_data, general_admin, rf
):
    request = rf.post("/", valid_price_list_form_data)
    request.user = general_admin

    use_fallback_message_storage(request)

    with translation.override("fi"):
        response = PriceListEditView.as_view()(
            request, price_list_id=price_list_with_product.pk
        )

    price_list_with_product.refresh_from_db()

    assert price_list_with_product.name == valid_price_list_form_data["name"]

    assert response.url == reverse(
        "respa_admin:edit-price-list",
        kwargs={
            "price_list_id": price_list_with_product.pk,
        },
    )


@pytest.mark.django_db
def test_price_list_copy_get(price_list_with_user_group_item, general_admin, rf):
    """
    Test that the form view has the price list items from the price list being copied.
    """

    price_list = price_list_with_user_group_item
    price_item = price_list.usergroup_prices.first()
    request = rf.get("/")
    request.user = general_admin
    with translation.override("fi"):
        response = PriceListCopyView.as_view()(request, price_list_id=price_list.pk)
        response.render()

    content = str(response.content)
    assert price_item.user_group.name in content
    assert str(price_item.price) in content


@pytest.mark.django_db
def test_price_list_copy_post(
    price_list_with_user_group_item, valid_price_list_copy_form_data, general_admin, rf
):
    """
    Test that new PriceList and UserGroupPriceListItem instaances are created.
    """

    assert PriceList.objects.count() == 1
    assert UserGroupPriceListItem.objects.count() == 1
    request = rf.post("/", valid_price_list_copy_form_data)
    request.user = general_admin

    use_fallback_message_storage(request)

    PriceListCopyView.as_view()(
        request, price_list_id=price_list_with_user_group_item.pk
    )

    assert PriceList.objects.count() == 2
    assert UserGroupPriceListItem.objects.count() == 2
