from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal
from functools import wraps

from django.db import transaction
from django.utils.timezone import now
from django.utils.translation import ugettext_lazy as _


def price_as_sub_units(price: Decimal) -> int:
    return int(round_price(price) * 100)


def round_price(price: Decimal) -> Decimal:
    return price.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def rounded(func):
    """
    Decorator for conditionally rounding function result

    By default the result is rounded to two decimal places, but the rounding
    can be turned off by giving parameter "rounded=False" when calling the
    function.
    """
    @wraps(func)
    def wrapped(*args, **kwargs):
        rounded = kwargs.pop('rounded', True)
        value = func(*args, **kwargs)
        if rounded:
            value = round_price(value)
        return value
    return wrapped


def convert_pretax_to_aftertax(pretax_price: Decimal, tax_percentage: Decimal) -> Decimal:
    return pretax_price * (1 + tax_percentage / 100)


def convert_aftertax_to_pretax(aftertax_price: Decimal, tax_percentage: Decimal) -> Decimal:
    return aftertax_price / (1 + tax_percentage / 100)


def get_price_period_display(price_period):
    if not price_period:
        return None

    hours = Decimal(price_period / timedelta(hours=1)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP).normalize()
    if hours == 1:
        return _('hour')
    else:
        return _('{hours} hours'.format(hours=hours))


def create_products_from_resource_pricelist(resource):
    from .models import Product

    resource_pricelist = resource.price_list
    if not resource_pricelist:
        return
    pricelist_items = resource_pricelist.price_list_items.all()

    for pricelist_item in pricelist_items:
        product = Product.objects.create(**{
            'sku': pricelist_item.id,
            'name_fi': pricelist_item.name,
            'price': pricelist_item.price,
            'price_type': pricelist_item.price_type,
            'price_period': pricelist_item.price_period,
            'tax_percentage': pricelist_item.tax_percentage,
            'pricelist_item': pricelist_item,
        })
        product.resources.add(resource)


@transaction.atomic
def archive_old_products_and_create_new_from_resource_pricelist(resource, old_pricelist):
    from .models import Product
    old_pricelist_items = old_pricelist.price_list_items.all()
    Product.objects.filter(pricelist_item__in=old_pricelist_items).update(archived_at=now())
    create_products_from_resource_pricelist(resource)
