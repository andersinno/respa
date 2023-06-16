import pytest

from payments.factories import ProductFactory
from resources.models import Resource, ResourceType

from .factories import (
    EventTypeFactory,
    PricedProductFactory,
    PriceListFactory,
    UserGroupFactory,
    UserGroupPriceListItemFactory,
)


@pytest.fixture
def user_group():
    return UserGroupFactory()


@pytest.fixture
def event_type():
    return EventTypeFactory()


@pytest.fixture
def price_list():
    return PriceListFactory()


@pytest.fixture
def price_list_with_product(resource):
    price_list = PriceListFactory()
    PricedProductFactory(
        product=ProductFactory(resources=[resource]), price_list=price_list
    )
    return price_list


@pytest.fixture
def price_list_with_user_group_item(price_list, user_group):
    UserGroupPriceListItemFactory(
        price_list=price_list, user_group=user_group, price=10.0
    )
    return price_list


@pytest.fixture
def resource_type():
    return ResourceType.objects.get_or_create(
        id="test_space", name="test_space", main_type="space"
    )[0]


@pytest.fixture
def resource(resource_type):
    return Resource.objects.create(
        type=resource_type, authentication="none", name="Resource"
    )


@pytest.fixture
def resource_2(resource_type):
    return Resource.objects.create(
        type=resource_type, authentication="none", name="Resource 2"
    )
