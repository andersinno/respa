import pytest

from .factories import (
    PriceListTemplateFactory,
    UserGroupPriceListTemplateItemFactory,
    ProductFactory,
    EventTypePriceListTemplateItemFactory,
)


@pytest.fixture
def product(resource):
    return ProductFactory(resources=[resource])


@pytest.mark.django_db
def test_create_price_list_from_template():
    """Should create a new price list from a template, including user group and
    event type items."""

    template = PriceListTemplateFactory()
    user_group_template = UserGroupPriceListTemplateItemFactory(template=template)
    event_type_template = EventTypePriceListTemplateItemFactory(template=template)

    price_list = template.create_price_list(name="new price list")

    assert price_list.name == "new price list"

    user_group_items = price_list.usergroup_prices.all()
    assert user_group_items.count() == 1

    item = user_group_items.first()

    assert item.user_group == user_group_template.user_group
    assert item.template == user_group_template
    assert item.price == user_group_template.price
    assert item.tax_percentage == user_group_template.tax_percentage

    event_type_items = price_list.event_prices.all()
    assert event_type_items.count() == 1

    item = event_type_items.first()

    assert item.event_type == event_type_template.event_type
    assert item.template == event_type_template
    assert item.price == event_type_template.price
    assert item.tax_percentage == event_type_template.tax_percentage


@pytest.mark.django_db
def test_update_price_list_from_template():
    """Price lists connected to a template should be updated on saving."""

    template = PriceListTemplateFactory(include_other_event_type_option=True)

    price_list = template.create_price_list(name="new price list")

    assert price_list.include_other_event_type_option is True
    assert price_list.template == template

    template.include_other_event_type_option = False
    template.save()

    price_list.refresh_from_db()
    assert price_list.include_other_event_type_option is False


@pytest.mark.django_db
def test_delete_user_group_item_from_template():
    """When deleting a user group item, the template should remove the corresponding
    user group items from all connected price lists."""

    template = PriceListTemplateFactory()
    user_group_template = UserGroupPriceListTemplateItemFactory(template=template)

    price_list = template.create_price_list(name="new price list")
    assert price_list.usergroup_prices.count() == 1

    user_group_template.delete()
    assert price_list.usergroup_prices.count() == 0


@pytest.mark.django_db
def test_update_user_group_item_template():
    """If a user group item in a template is updated, all connected items should
    also be updated."""

    template = PriceListTemplateFactory()

    user_group_template = UserGroupPriceListTemplateItemFactory(
        template=template,
        price=333,
    )

    price_list = template.create_price_list(name="new price list")

    user_group_item = price_list.usergroup_prices.first()
    assert user_group_item.price == 333

    user_group_template.price = 444
    user_group_template.save()

    user_group_item.refresh_from_db()
    assert user_group_item.price == 444


@pytest.mark.django_db
def test_add_user_group_item_template():
    """If a user group item in a template is added, all connected price lists should
    add this item."""

    template = PriceListTemplateFactory()

    # existing item
    UserGroupPriceListTemplateItemFactory(
        template=template,
        price=333,
    )

    price_list = template.create_price_list(name="new price list")

    user_group_item = price_list.usergroup_prices.first()
    assert user_group_item.price == 333

    user_group_item.refresh_from_db()
    assert user_group_item.price == 333

    # new item
    new_template = UserGroupPriceListTemplateItemFactory(
        template=template,
        price=111,
    )

    # original item should be untouched
    user_group_item.refresh_from_db()
    assert user_group_item.price == 333

    new_item = price_list.usergroup_prices.get(template=new_template)
    assert new_item.price == 111


@pytest.mark.django_db
def test_delete_event_type_item_from_template():
    """When deleting an even type item, the template should remove the corresponding
    items from all connected price lists."""

    template = PriceListTemplateFactory()
    event_type_template = EventTypePriceListTemplateItemFactory(template=template)

    price_list = template.create_price_list(name="new price list")
    assert price_list.event_prices.count() == 1

    event_type_template.delete()
    assert price_list.event_prices.count() == 0


@pytest.mark.django_db
def test_update_event_type_item_template():
    """If an event type item in a template is updated, all connected items should
    also be updated."""

    template = PriceListTemplateFactory()

    event_type_template = EventTypePriceListTemplateItemFactory(
        template=template,
        price=333,
    )

    price_list = template.create_price_list(name="new price list")

    event_type_item = price_list.event_prices.first()
    assert event_type_item.price == 333

    event_type_template.price = 444
    event_type_template.save()

    event_type_item.refresh_from_db()
    assert event_type_item.price == 444


@pytest.mark.django_db
def test_add_event_type_item_template():
    """If a user group item in a template is added, all connected price lists should
    add this item."""

    template = PriceListTemplateFactory()

    # existing item
    EventTypePriceListTemplateItemFactory(
        template=template,
        price=333,
    )

    price_list = template.create_price_list(name="new price list")

    event_type_item = price_list.event_prices.first()
    assert event_type_item.price == 333

    event_type_item.refresh_from_db()
    assert event_type_item.price == 333

    # new item
    new_template = EventTypePriceListTemplateItemFactory(
        template=template,
        price=111,
    )

    # original item should be untouched
    event_type_item.refresh_from_db()
    assert event_type_item.price == 333

    new_item = price_list.event_prices.get(template=new_template)
    assert new_item.price == 111
