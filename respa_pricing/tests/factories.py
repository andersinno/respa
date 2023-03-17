import factory
import factory.fuzzy
import factory.random

from decimal import Decimal

from payments.factories import ProductFactory

from ..models import (
    EventType,
    EventTypePriceListItem,
    PriceList,
    PricedProduct,
    UserGroup,
    UserGroupPriceListItem,
)


class PriceListFactory(factory.django.DjangoModelFactory):
    """Mock PriceList objects, with price list items"""

    name = factory.Faker("catch_phrase")

    class Meta:
        model = PriceList


class UserGroupFactory(factory.django.DjangoModelFactory):
    """Mock UserGroup objects"""

    name = factory.Faker("catch_phrase")

    class Meta:
        model = UserGroup


class EventTypeFactory(factory.django.DjangoModelFactory):
    """Mock EventType objects"""

    name = factory.Faker("catch_phrase")

    class Meta:
        model = EventType


class UserGroupPriceListItemFactory(factory.django.DjangoModelFactory):
    """Mock UserGroupPriceListItem objects"""

    price_list = factory.SubFactory(PriceListFactory)
    user_group = factory.SubFactory(UserGroupFactory)
    price = Decimal("10.0")
    tax_percentage = Decimal("14.0")

    class Meta:
        model = UserGroupPriceListItem


class EventTypePriceListItemFactory(factory.django.DjangoModelFactory):
    """Mock EventTypePriceListItem objects"""

    price_list = factory.SubFactory(PriceListFactory)
    event_type = factory.SubFactory(EventTypeFactory)
    price = Decimal("20.0")
    tax_percentage = Decimal("24.0")

    class Meta:
        model = EventTypePriceListItem


class PricedProductFactory(factory.django.DjangoModelFactory):
    """Mock PricedProduct objects"""

    product = factory.SubFactory(ProductFactory)
    price_list = factory.SubFactory(PriceListFactory)

    class Meta:
        model = PricedProduct
