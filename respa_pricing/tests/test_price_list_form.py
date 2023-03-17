import pytest

from payments.models import Product
from resources.models import Resource

from ..forms import PriceListForm


@pytest.mark.django_db
def test_priced_products_are_created_from_selected_resources(
    price_list, resource, resource_2
):
    """
    Test that, when a price list form is saved, products and
    priced products are created from any new selected resources.
    """
    assert Product.objects.current().count() == 0
    assert price_list.priced_products.count() == 0

    resources = Resource.objects.filter(pk__in=[resource.pk, resource_2.pk])
    form = PriceListForm(
        {"name": price_list.name, "resources": resources}, instance=price_list
    )
    form.save()

    assert Product.objects.current().count() == 2
    assert price_list.priced_products.count() == 2


@pytest.mark.django_db
def test_removed_resource_products_are_archived(price_list_with_products):
    """
    Test that, when a price list form is saved, the priced products
    for the unselected resources are deleted and the products archived.
    """
    assert Product.objects.current().count() == 2
    assert price_list_with_products.priced_products.count() == 2

    form = PriceListForm(
        {"name": price_list_with_products.name, "resources": Resource.objects.none()},
        instance=price_list_with_products,
    )
    form.save()

    assert Product.objects.current().count() == 0
    assert price_list_with_products.priced_products.count() == 0
