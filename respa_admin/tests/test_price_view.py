import pytest
from django.utils import translation
from ..views.prices import PriceListCreateView


@pytest.mark.django_db
def test_price_list_create_get(general_admin, user_group, event_type, rf):
    request = rf.get("/")
    request.user = general_admin
    with translation.override("fi"):
        response = PriceListCreateView.as_view()(request)
        response.render()

    content = str(response.content)
    assert user_group.name in content
    assert event_type.name in content
