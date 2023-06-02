import factory
import factory.fuzzy
import factory.random

from decimal import Decimal

from payments.factories import ProductFactory

from ..models import (
    EventType,
    EventTypePriceListItem,
    EventTypePriceListTemplateItem,
    PriceList,
    PricedProduct,
    UserGroup,
    UserGroupPriceListItem,
    UserGroupPriceListTemplateItem,
    PriceListTemplate,
)


class PriceListTemplateFactory(factory.django.DjangoModelFactory):
    name = factory.Faker("catch_phrase")

    class Meta:
        model = PriceListTemplate


class PriceListFactory(factory.django.DjangoModelFactory):
    """Mock PriceList objects, with price list items"""

    name = factory.Faker("catch_phrase")

    class Meta:
        model = PriceList


class UserGroupFactory(factory.django.DjangoModelFactory):
    """Mock UserGroup objects"""

    name_en = factory.Faker("catch_phrase")
    name_fi = factory.Faker("catch_phrase")

    tax_percentage = Decimal("24.00")

    class Meta:
        model = UserGroup


class EventTypeFactory(factory.django.DjangoModelFactory):
    """Mock EventType objects"""

    name_en = factory.Faker("catch_phrase")
    name_fi = factory.Faker("catch_phrase")

    tax_percentage = Decimal("14.00")

    class Meta:
        model = EventType


class UserGroupPriceListTemplateItemFactory(factory.django.DjangoModelFactory):
    """Mock UserGroupPriceListItem objects"""

    template = factory.SubFactory(PriceListTemplateFactory)
    user_group = factory.SubFactory(UserGroupFactory)
    price = Decimal("10.0")

    class Meta:
        model = UserGroupPriceListTemplateItem


class UserGroupPriceListItemFactory(factory.django.DjangoModelFactory):
    """Mock UserGroupPriceListItem objects"""

    price_list = factory.SubFactory(PriceListFactory)
    user_group = factory.SubFactory(UserGroupFactory)
    price = Decimal("10.0")

    class Meta:
        model = UserGroupPriceListItem


class EventTypePriceListTemplateItemFactory(factory.django.DjangoModelFactory):
    """Mock EventTypePriceListItem objects"""

    template = factory.SubFactory(PriceListTemplateFactory)
    event_type = factory.SubFactory(EventTypeFactory)
    price = Decimal("20.0")

    class Meta:
        model = EventTypePriceListTemplateItem


class EventTypePriceListItemFactory(factory.django.DjangoModelFactory):
    """Mock EventTypePriceListItem objects"""

    price_list = factory.SubFactory(PriceListFactory)
    event_type = factory.SubFactory(EventTypeFactory)
    price = Decimal("20.0")

    class Meta:
        model = EventTypePriceListItem


class PricedProductFactory(factory.django.DjangoModelFactory):
    """Mock PricedProduct objects"""

    product = factory.SubFactory(ProductFactory)
    price_list = factory.SubFactory(PriceListFactory)

    class Meta:
        model = PricedProduct
