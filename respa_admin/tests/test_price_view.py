import pytest
from django.utils import translation
from django.urls import reverse
from ..views.prices import PriceListCreateView
from respa_pricing.models import PriceList


@pytest.mark.django_db
def test_price_list_create_get(user_group, event_type, general_admin, rf):
    request = rf.get("/")
    request.user = general_admin
    with translation.override("fi"):
        response = PriceListCreateView.as_view()(request)
        response.render()

    content = str(response.content)
    assert user_group.name in content
    assert event_type.name in content


@pytest.mark.django_db
def test_price_list_create_post_empty(empty_price_list_form_data, general_admin, rf):
    request = rf.post("/", empty_price_list_form_data)
    request.user = general_admin
    with translation.override("fi"):
        response = PriceListCreateView.as_view()(request)

    assert response.status_code == 200
    assert response.context_data["form"].errors


@pytest.mark.django_db
def test_price_list_create_post_complete(valid_price_list_form_data, general_admin, rf):
    request = rf.post("/", valid_price_list_form_data)
    request.user = general_admin
    with translation.override("fi"):
        response = PriceListCreateView.as_view()(request)

    new_price_list = PriceList.objects.get()
    assert new_price_list.name == valid_price_list_form_data["name"]

    assert response.url == reverse(
        "respa_admin:edit-price-list", kwargs={"price_list_id": new_price_list.pk}
    )
