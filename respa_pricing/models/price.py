from datetime import datetime, timedelta
from decimal import Decimal

from django.db import models
from django.utils.duration import duration_string
from django.utils.timezone import now
from django.utils.translation import ugettext_lazy as _
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator

from payments.utils import (
    rounded,
    convert_aftertax_to_pretax,
    convert_pretax_to_aftertax,
)
from .utils import generate_id



TAX_PERCENTAGES = [Decimal(x) for x in (
    '0.00',
    '10.00',
    '14.00',
    '24.00',
)]

DEFAULT_TAX_PERCENTAGE = Decimal('24.00')

PRICE_PER_PERIOD = 'per_period'
PRICE_FIXED = 'fixed'
PRICE_TYPE_CHOICES = (
    (PRICE_PER_PERIOD, _('per period')),
    (PRICE_FIXED, _('fixed')),
)


class AutoIdentifiedModelMixin:
    def save(self, *args, **kwargs):
        pk_type = self._meta.pk.get_internal_type()
        if pk_type == 'CharField':
            if not self.pk:
                self.pk = generate_id()
        elif pk_type == 'AutoField':
            pass
        else:
            raise Exception('Unsupported primary key field: %s' % pk_type)
        super().save(*args, **kwargs)


class UserGroup(AutoIdentifiedModelMixin, models.Model):
    id = models.CharField(primary_key=True, max_length=100)
    name = models.CharField(verbose_name=_('Name'), max_length=200)

    def __str__(self):
        return self.name


class Event(AutoIdentifiedModelMixin, models.Model):
    id = models.CharField(primary_key=True, max_length=100)
    name = models.CharField(verbose_name=_('Name'), max_length=200)

    def __str__(self):
        return self.name


class PriceList(models.Model):
    name = models.CharField(
        verbose_name=_('Name'),
        max_length=100,
    )
    needs_manual_confirmation = models.BooleanField(default=False)

    def __str__(self):
        return self.name


    @classmethod
    def get_price_info(cls, product, user_group_id, event_type_id, begin, end):
        """
        While choosing the price source, following rules apply:
        Price source means either user group or event type as price is
        attached to them.

        It should always choose the source with higher price (before tax) and
        lower tax source and apply that tax percentage with an exception.
        E.g. If the user chooses

        - UsergroupPriceItem X (price_before_tax = 20, tax_percentage = 24)
        - EventPriceItem Y (price_before_tax = 15, tax_percentage = 14)

        Then the price should be 20 and tax_percentage should be 14.

        ** Exception: If any price is zero, that should take precedence.
        """
        @rounded
        def _getpre_tax_to_after_tax(pretax_price, tax_percentage):
            return convert_pretax_to_aftertax(pretax_price, tax_percentage)

        price_list = PricedProduct.objects.get(product=product).price_list
        price_source = tax_source = user_group_item = price_list.usergroup_prices.filter(user_group__id=user_group_id).first()
        pre_tax_price = pre_tax_price_by_user_group = user_group_item.get_pretax_price_for_time_range(begin, end)
        event_item = price_list.event_prices.filter(event__id=event_type_id).first()

        if event_item and pre_tax_price_by_user_group != 0:
            pre_tax_price_by_event = event_item.get_pretax_price_for_time_range(begin, end)
            tax_source = user_group_item if user_group_item.tax_percentage < event_item.tax_percentage else event_item
            if (pre_tax_price_by_event >= pre_tax_price_by_user_group) or pre_tax_price_by_event == 0:
                price_source = event_item
                pre_tax_price = pre_tax_price_by_event

        price_details = price_source.get_price_details()
        price_after_tax = _getpre_tax_to_after_tax(pre_tax_price, tax_source.tax_percentage)
        price_details['total_price'] = str(price_after_tax)
        price_details['amount'] = str(_getpre_tax_to_after_tax(price_source.price, tax_source.tax_percentage))
        price_details['tax_percentage'] = str(tax_source.tax_percentage)
        price_details['price_source'] = price_source
        return price_details

    def archive_old_products_and_create_new_ones(self, resource, old_pricelist):
        old_pricelist.archive_old_products()
        self.create_related_products(resource)

    def unarchive_products(self):
        from payments.models import Product, ARCHIVED_AT_NONE
        current_priced_products = self.priced_products.all()
        current_product_ids = [p.product.id for p in current_priced_products]
        Product.objects.filter(id__in=current_product_ids).update(archived_at=ARCHIVED_AT_NONE)

    def archive_old_products(self):
        from payments.models import Product
        previous_priced_products = self.priced_products.all()
        previous_product_ids = [p.product.id for p in previous_priced_products]
        Product.objects.filter(id__in=previous_product_ids).update(archived_at=now())

    def create_related_products(self, resource):
        from payments.models import Product
        product = Product.objects.create(
            name=self.name + 'product',
            # sku='demo_001',
            sku=resource.pk,
            product_id=generate_id(),
        )
        product.resources.add(resource)
        PricedProduct.objects.create(product=product, price_list=self)


class PricedProduct(models.Model):
    product = models.OneToOneField('payments.Product', on_delete=models.CASCADE)
    price_list = models.ForeignKey(
        PriceList,
        related_name='priced_products',
        on_delete=models.SET_NULL,
        null=True,
    )


class GeneralPriceItem(models.Model):
    price = models.DecimalField(
        verbose_name=_('price including VAT'), max_digits=10, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    tax_percentage = models.DecimalField(
        verbose_name=_('tax percentage'), max_digits=5, decimal_places=2, default=DEFAULT_TAX_PERCENTAGE,
        choices=[(tax, str(tax)) for tax in TAX_PERCENTAGES]
    )
    price_period = models.DurationField(
        verbose_name=_('price period'), null=True, blank=True, default=timedelta(hours=1),
    )
    price_type = models.CharField(
        max_length=32, verbose_name=_('price type'), choices=PRICE_TYPE_CHOICES, default=PRICE_PER_PERIOD
    )

    class Meta:
        abstract = True

    def clean(self):
        if self.price_type == PRICE_PER_PERIOD:
            if not self.price_period:
                raise ValidationError(
                    {'price_period': _('This field requires a non-zero value when price type is "per period".')}
                )
        else:
            self.price_period = None

    def get_price_for_reservation(self, begin, end):
        return self.get_price_for_time_range(begin, end)

    @rounded
    def get_price_for_time_range(self, begin, end):
        assert begin < end

        if self.price_type == PRICE_FIXED:
            return self.price
        elif self.price_type == PRICE_PER_PERIOD:
            assert self.price_period, '{} {}'.format(self, self.price_period)
            return self.price * Decimal((end - begin) / self.price_period)
        else:
            raise NotImplementedError('Cannot calculate price, unknown price type "{}".'.format(self.price_type))

    def get_price_details(self):
        if self.price_type not in (PRICE_FIXED, PRICE_PER_PERIOD):
            raise ValueError('{} has invalid price type "{}"'.format(self, self.price_type))
        price_details = {
            'type': self.price_type,
            'tax_percentage': str(self.tax_percentage),
            'amount': str(self.price)
        }
        if self.price_type == PRICE_PER_PERIOD:
            price_details.update({'period': duration_string(self.price_period)})

        return price_details

    @rounded
    def get_pretax_price(self) -> Decimal:
        return convert_aftertax_to_pretax(self.price, self.tax_percentage)

    @rounded
    def get_pretax_price_for_time_range(self, begin: datetime, end: datetime) -> Decimal:
        return convert_aftertax_to_pretax(self.get_price_for_time_range(begin, end), self.tax_percentage)


class EventPriceListItem(GeneralPriceItem):
    price_list = models.ForeignKey(
        PriceList,
        related_name='event_prices',
        on_delete=models.CASCADE,
    )
    event = models.ForeignKey(
        Event,
        related_name='pricelist_items',
        on_delete=models.CASCADE,
    )

    def __str__(self):
        return f'{self.price}:{self.event.name}'


class UserGroupPriceListItem(GeneralPriceItem):
    price_list = models.ForeignKey(
        PriceList,
        related_name='usergroup_prices',
        on_delete=models.CASCADE,
    )
    user_group = models.ForeignKey(
        UserGroup,
        related_name='pricelist_items',
        on_delete=models.CASCADE,
    )

    def __str__(self):
        return f'{self.price}:{self.user_group.name}'

