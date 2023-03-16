import pytest
from guardian.shortcuts import assign_perm
from rest_framework.reverse import reverse

from ..factories import ProductFactory


PRICE_ENDPOINT_ORDER_FIELDS = {
    'order_lines', 'price', 'begin', 'end'
}

ORDER_LINE_FIELDS = {
    'product', 'quantity', 'price', 'unit_price'
}

PRODUCT_FIELDS = {
    'id', 'type', 'name', 'description'
}

PRICE_FIELDS = {'type'}


def get_detail_url(order):
    return reverse('order-detail', kwargs={'order_number': order.order_number})


@pytest.fixture(autouse=True)
def auto_use_django_db(db):
    pass


@pytest.fixture
def product(resource_in_unit):
    return ProductFactory(resources=[resource_in_unit])


@pytest.fixture
def product_2(resource_in_unit):
    return ProductFactory(resources=[resource_in_unit])
