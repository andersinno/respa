import pytest

from payments.models import Product

from ..forms import PriceListForm
from ..models import PricedProduct


@pytest.mark.django_db
def test_priced_products_are_created_from_selected_resources(price_list, resource):
    """
    Test that, when a price list form is saved, product and
    priced product are created from any new selected resource.
    """
    assert Product.objects.current().count() == 0
    assert PricedProduct.objects.count() == 0

    form = PriceListForm(
        {"name": price_list.name, "resource": resource.pk}, instance=price_list
    )
    form.save()

    assert Product.objects.current().count() == 1
    assert PricedProduct.objects.count() == 1


@pytest.mark.django_db
def test_removed_resource_products_are_archived(price_list_with_product):
    """
    Test that, when a price list form is saved, the priced product
    for the unselected resource is deleted and the product is archived.
    """
    assert Product.objects.current().count() == 1
    assert PricedProduct.objects.count() == 1

    form = PriceListForm(
        {"name": price_list_with_product.name, "resource": None},
        instance=price_list_with_product,
    )
    form.save()

    assert Product.objects.current().count() == 0
    assert PricedProduct.objects.count() == 0
