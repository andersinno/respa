from datetime import datetime, timedelta
from decimal import Decimal

from django.db import models
from django.utils.duration import duration_string
from django.utils.translation import ugettext_lazy as _
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator

from payments.utils import (
    rounded,
    convert_aftertax_to_pretax,
    convert_pretax_to_aftertax,
)
from resources.models import Resource

from .utils import generate_id


TAX_PERCENTAGES = [
    Decimal(x)
    for x in (
        "0.00",
        "10.00",
        "14.00",
        "24.00",
    )
]

DEFAULT_TAX_PERCENTAGE = Decimal("24.00")

PRICE_PER_PERIOD = "per_period"
PRICE_FIXED = "fixed"
PRICE_TYPE_CHOICES = (
    (PRICE_PER_PERIOD, _("per period")),
    (PRICE_FIXED, _("fixed")),
)


class AutoIdentifiedModelMixin:
    def save(self, *args, **kwargs):
        pk_type = self._meta.pk.get_internal_type()
        if pk_type == "CharField":
            if not self.pk:
                self.pk = generate_id()
        elif pk_type == "AutoField":
            pass
        else:
            raise Exception("Unsupported primary key field: %s" % pk_type)
        super().save(*args, **kwargs)


class UserGroup(AutoIdentifiedModelMixin, models.Model):
    id = models.CharField(primary_key=True, max_length=100)
    name = models.CharField(verbose_name=_("Name"), max_length=200)
    tax_percentage = models.DecimalField(
        verbose_name=_("tax percentage"),
        max_digits=5,
        decimal_places=2,
        default=DEFAULT_TAX_PERCENTAGE,
        choices=[(tax, str(tax)) for tax in TAX_PERCENTAGES],
    )

    class Meta:
        verbose_name = _("User group")
        verbose_name_plural = _("User groups")

    def __str__(self):
        return self.name


class EventType(AutoIdentifiedModelMixin, models.Model):
    id = models.CharField(primary_key=True, max_length=100)
    name = models.CharField(verbose_name=_("Name"), max_length=200)
    tax_percentage = models.DecimalField(
        verbose_name=_("tax percentage"),
        max_digits=5,
        decimal_places=2,
        default=DEFAULT_TAX_PERCENTAGE,
        choices=[(tax, str(tax)) for tax in TAX_PERCENTAGES],
    )

    class Meta:
        verbose_name = _("Event type")
        verbose_name_plural = _("Event types")

    def __str__(self):
        return self.name


class PriceListQuerySet(models.QuerySet):
    def modifiable_by(self, user):
        modifiable_resources_by_user = Resource.objects.modifiable_by(user)
        return self.filter(
            priced_product__product__resources__pk__in=modifiable_resources_by_user
        )


class PriceList(models.Model):
    name = models.CharField(
        verbose_name=_("Name"),
        max_length=100,
    )

    objects = PriceListQuerySet.as_manager()

    class Meta:
        verbose_name = _("Price list")
        verbose_name_plural = _("Price lists")

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

        - UserGroupPriceListItem X (price_before_tax = 20, tax_percentage = 24)
        - EventTypePriceListItem Y (price_before_tax = 15, tax_percentage = 14)

        Then the price should be 20 and tax_percentage should be 14.

        ** Exception: If any price is zero, that should take precedence.
        """

        @rounded
        def _pre_tax_to_after_tax(pretax_price, tax_percentage):
            return convert_pretax_to_aftertax(pretax_price, tax_percentage)

        price_list = PricedProduct.objects.get(product=product).price_list
        user_group_item = price_list.usergroup_prices.filter(
            user_group__id=user_group_id
        ).first()

        price_source = tax_source = user_group_item

        pre_tax_price_by_user_group = user_group_item.get_pretax_price_for_time_range(
            begin, end
        )
        pre_tax_price = pre_tax_price_by_user_group

        event_item = price_list.event_prices.filter(
            event_type__id=event_type_id
        ).first()

        if event_item and pre_tax_price_by_user_group != 0:
            pre_tax_price_by_event = event_item.get_pretax_price_for_time_range(
                begin, end
            )
            tax_source = (
                user_group_item
                if user_group_item.tax_percentage < event_item.tax_percentage
                else event_item
            )
            if (
                pre_tax_price_by_event >= pre_tax_price_by_user_group
            ) or pre_tax_price_by_event == 0:
                price_source = event_item
                pre_tax_price = pre_tax_price_by_event

        price_details = price_source.get_price_details()
        price_after_tax = _pre_tax_to_after_tax(
            pre_tax_price, tax_source.tax_percentage
        )
        unit_price_pre_tax = convert_aftertax_to_pretax(
            price_source.price, price_source.tax_percentage
        )
        unit_price_after_tax = _pre_tax_to_after_tax(
            unit_price_pre_tax, tax_source.tax_percentage
        )
        price_details["total_price"] = str(price_after_tax)
        price_details["amount"] = str(unit_price_after_tax)
        price_details["tax_percentage"] = str(tax_source.tax_percentage)
        price_details["price_source"] = price_source
        return price_details


class PricedProduct(models.Model):
    product = models.OneToOneField("payments.Product", on_delete=models.CASCADE)
    price_list = models.OneToOneField(
        PriceList, on_delete=models.CASCADE, related_name="priced_product"
    )

    class Meta:
        verbose_name = _("Priced product")
        verbose_name_plural = _("Priced products")


class GeneralPriceListItem(models.Model):
    price = models.DecimalField(
        verbose_name=_("price including VAT"),
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    price_period = models.DurationField(
        verbose_name=_("price period"),
        null=True,
        blank=True,
        default=timedelta(hours=1),
    )
    price_type = models.CharField(
        max_length=32,
        verbose_name=_("price type"),
        choices=PRICE_TYPE_CHOICES,
        default=PRICE_PER_PERIOD,
    )

    class Meta:
        abstract = True

    def clean(self):
        if self.price_type == PRICE_PER_PERIOD:
            if not self.price_period:
                raise ValidationError(
                    {
                        "price_period": _(
                            'This field requires a non-zero value when price type is "per period".'
                        )
                    }
                )
        else:
            self.price_period = None

    def get_price_for_reservation(self, begin, end):
        return self.get_price_for_time_range(begin, end)

    @property
    def tax_percentage(self):
        """Implement this the subclass"""
        raise NotImplementedError

    @rounded
    def get_price_for_time_range(self, begin, end):
        assert begin < end

        if self.price_type == PRICE_FIXED:
            return self.price
        elif self.price_type == PRICE_PER_PERIOD:
            assert self.price_period, "{} {}".format(self, self.price_period)
            return self.price * Decimal((end - begin) / self.price_period)
        else:
            raise NotImplementedError(
                'Cannot calculate price, unknown price type "{}".'.format(
                    self.price_type
                )
            )

    def get_price_details(self):
        if self.price_type not in (PRICE_FIXED, PRICE_PER_PERIOD):
            raise ValueError(
                '{} has invalid price type "{}"'.format(self, self.price_type)
            )
        price_details = {
            "type": self.price_type,
            "tax_percentage": str(self.tax_percentage),
            "amount": str(self.price),
        }
        if self.price_type == PRICE_PER_PERIOD:
            price_details.update({"period": duration_string(self.price_period)})

        return price_details

    @rounded
    def get_pretax_price(self) -> Decimal:
        return convert_aftertax_to_pretax(self.price, self.tax_percentage)

    @rounded
    def get_pretax_price_for_time_range(
        self, begin: datetime, end: datetime
    ) -> Decimal:
        return convert_aftertax_to_pretax(
            self.get_price_for_time_range(begin, end), self.tax_percentage
        )


class EventTypePriceListItem(GeneralPriceListItem):
    price_list = models.ForeignKey(
        PriceList,
        related_name="event_prices",
        on_delete=models.CASCADE,
        verbose_name=_("price list"),
    )
    event_type = models.ForeignKey(
        EventType,
        related_name="pricelist_items",
        on_delete=models.CASCADE,
        verbose_name=_("event type"),
    )

    class Meta:
        verbose_name = _("Event type price")
        verbose_name_plural = _("Event type prices")

    @property
    def tax_percentage(self):
        return self.event_type.tax_percentage

    def __str__(self):
        return f"{self.price}:{self.event_type.name}"


class UserGroupPriceListItem(GeneralPriceListItem):
    price_list = models.ForeignKey(
        PriceList,
        related_name="usergroup_prices",
        on_delete=models.CASCADE,
        verbose_name=_("price list"),
    )
    user_group = models.ForeignKey(
        UserGroup,
        related_name="pricelist_items",
        on_delete=models.CASCADE,
        verbose_name=_("user group"),
    )

    class Meta:
        verbose_name = _("User group price")
        verbose_name_plural = _("User group prices")

    @property
    def tax_percentage(self):
        return self.user_group.tax_percentage

    def __str__(self):
        return f"{self.price}:{self.user_group.name}"
