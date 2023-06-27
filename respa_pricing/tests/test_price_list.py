import datetime
import pytest
from decimal import Decimal
from pytz import UTC

from payments.factories import ProductFactory

from ..models import PriceList
from .factories import EventTypePriceListItemFactory, UserGroupPriceListItemFactory


@pytest.mark.django_db
def test_get_price_info_with_no_priced_product(
    price_list, user_group, event_type, resource
):
    begin = datetime.datetime(2119, 5, 5, 10, 0, 0, tzinfo=UTC)
    end = datetime.datetime(2119, 5, 5, 12, 0, 0, tzinfo=UTC)
    price_info = PriceList.get_price_info(
        ProductFactory(resources=[resource]), user_group.id, event_type.id, begin, end
    )
    assert price_info == {
        "total_price": 0,
        "amount": 0,
        "price_source": None,
    }


@pytest.mark.django_db
def test_get_price_info_with_no_user_group_item(
    price_list_with_product, user_group, event_type, resource
):
    begin = datetime.datetime(2119, 5, 5, 10, 0, 0, tzinfo=UTC)
    end = datetime.datetime(2119, 5, 5, 12, 0, 0, tzinfo=UTC)

    product = price_list_with_product.priced_product.product
    price_info = PriceList.get_price_info(
        product, user_group.id, event_type.id, begin, end
    )

    assert price_info == {
        "total_price": 0,
        "amount": 0,
        "price_source": None,
    }


@pytest.mark.django_db
def test_get_price_info_returns_highest_price_and_lowest_tax_pct(
    price_list_with_product, user_group, event_type
):
    """
    Test that PriceList.get_price_info() returns the highest price (before tax) and
    lower tax percentage.

    E.g. If the price list the following items:

    - UserGroupPriceListItem X (price_before_tax = 20, tax_percentage = 24)
    - EventTypePriceListItem Y (price_before_tax = 15, tax_percentage = 14)

    Then the returned unit price (before tax) should be 20 and tax_percentage
    should be 14.
    """

    user_group_price_list_item = UserGroupPriceListItemFactory(
        price_list=price_list_with_product,
        price=Decimal("24.80"),
        user_group=user_group,
    )
    EventTypePriceListItemFactory(
        price_list=price_list_with_product,
        price=Decimal("17.10"),
        event_type=event_type,
    )

    product = price_list_with_product.priced_product.product
    begin = datetime.datetime(2119, 5, 5, 10, 0, 0, tzinfo=UTC)
    end = datetime.datetime(2119, 5, 5, 12, 0, 0, tzinfo=UTC)
    price_info = PriceList.get_price_info(
        product, user_group.id, event_type.id, begin, end
    )

    assert price_info["price_source"] == user_group_price_list_item
    assert price_info["tax_percentage"] == str(Decimal("14.00"))
    assert price_info["amount"] == str(Decimal("22.80"))
    assert price_info["total_price"] == str(Decimal("45.60"))
