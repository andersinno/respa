from datetime import datetime, timedelta
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils.duration import duration_string
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from django.utils.timezone import now

from payments.utils import (
    convert_aftertax_to_pretax,
    convert_pretax_to_aftertax,
    rounded,
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
        "25.50",
    )
]

DEFAULT_TAX_PERCENTAGE = Decimal("25.50")

PRICE_PER_PERIOD = "per_period"
PRICE_FIXED = "fixed"
PRICE_MIXED = "mixed"
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
        return f"{self.name} (ALV {self.tax_percentage}%)"


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
        return f"{self.name} (ALV {self.tax_percentage}%)"


class PriceListTemplate(models.Model):
    name = models.CharField(
        verbose_name=_("Name"),
        max_length=100,
    )
    include_other_event_type_option = models.BooleanField(
        verbose_name=_("include other event type option"),
        default=True,
        help_text=_(
            'Designates whether a "None of the above" option, '
            "that doesn't affect the price, "
            "should be added to the event type options."
        ),
    )

    template_fields = ["include_other_event_type_option"]

    class Meta:
        verbose_name = _("Price list template")
        verbose_name_plural = _("Price list templates")

    def __str__(self):
        return self.name

    def save(self, **kwargs):
        is_new = self.pk is None
        super().save(**kwargs)
        if not is_new:
            price_lists_for_update = []
            price_lists = self.price_lists.all()

            for price_list in price_lists:
                for field in self.template_fields:
                    setattr(price_list, field, getattr(self, field))
                price_lists_for_update.append(price_list)

            if price_lists_for_update:
                price_lists.bulk_update(
                    price_lists_for_update, fields=self.template_fields
                )

    def add_price_list(self, price_list):
        """Saves a PriceList instance with all fields based on template.

        User groups and event types are also created.
        """

        price_list.template = self

        for field in self.template_fields:
            setattr(price_list, field, getattr(self, field))

        price_list.save()

        user_group_items = [
            template.make_item(price_list)
            for template in self.usergroup_prices.select_related("user_group")
        ]

        if user_group_items:
            UserGroupPriceListItem.objects.bulk_create(user_group_items)

        event_type_items = [
            template.make_item(price_list)
            for template in self.event_prices.select_related("event_type")
        ]

        if event_type_items:
            EventTypePriceListItem.objects.bulk_create(event_type_items)

        return price_list


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
    include_other_event_type_option = models.BooleanField(
        verbose_name=_("include other event type option"),
        default=True,
        help_text=_(
            'Designates whether a "None of the above" option, '
            "that doesn't affect the price, "
            "should be added to the event type options."
        ),
    )

    template = models.ForeignKey(
        PriceListTemplate,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="price_lists",
    )

    objects = PriceListQuerySet.as_manager()

    class Meta:
        verbose_name = _("Price list")
        verbose_name_plural = _("Price lists")

    def __str__(self):
        return self.name

    def delete(self, *args, **kwargs):
        priced_product = getattr(self, "priced_product", None)
        if priced_product:
            priced_product.product.archived_at = now()
            priced_product.product.save()
        super().delete(*args, **kwargs)

    @cached_property
    def price_type(self):
        price_types = (
            self.usergroup_prices.union(self.event_prices.all())
            .values_list("price_type", flat=True)
            .distinct()
        )

        if not price_types:
            return None

        if len(price_types) > 1 or PRICE_PER_PERIOD in price_types:
            return PRICE_MIXED

        return PRICE_FIXED

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

        If no price list found for priced product or price list does not have
        a user group price item, returns:
            {
                "total_price": 0,
                "amount": 0,
                "price_source": None,
            }
        """

        try:
            price_list = PricedProduct.objects.get(product=product).price_list
        except PricedProduct.DoesNotExist:
            return {
                "total_price": 0,
                "amount": 0,
                "price_source": None,
            }

        user_group_item = price_list.usergroup_prices.filter(
            user_group__id=user_group_id
        ).first()

        if user_group_item is None:
            return {
                "total_price": 0,
                "amount": 0,
                "price_source": None,
            }

        price_source = tax_source = user_group_item

        pre_tax_price_by_user_group = user_group_item.get_pretax_price_for_time_range(
            begin, end, rounded=False
        )
        pre_tax_price = pre_tax_price_by_user_group

        event_item = price_list.event_prices.filter(
            event_type__id=event_type_id
        ).first()

        if event_item and pre_tax_price_by_user_group != 0:
            pre_tax_price_by_event = event_item.get_pretax_price_for_time_range(
                begin, end, rounded=False
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
                            'This field requires a non-zero value when price type is "per period".'  # noqa
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


class EventTypeTaxPercentage:
    """Mixin class for calculating event type tax percentage."""

    @property
    def tax_percentage(self):
        return self.event_type.tax_percentage


class EventTypePriceListTemplateItem(EventTypeTaxPercentage, GeneralPriceListItem):
    template = models.ForeignKey(
        PriceListTemplate,
        related_name="event_prices",
        on_delete=models.CASCADE,
        verbose_name=_("template"),
    )

    event_type = models.ForeignKey(
        EventType,
        related_name="pricelist_template_items",
        on_delete=models.CASCADE,
        verbose_name=_("event type"),
    )

    class Meta:
        verbose_name = _("Event type price template")
        verbose_name_plural = _("Event type price templates")

    template_fields = [
        "event_type",
        "price",
        "price_period",
        "price_type",
    ]

    def __str__(self):
        return f"{self.price}:{self.event_type.name}"

    def save(self, **kwargs):
        is_new = self.pk is None
        super().save(**kwargs)
        if is_new:
            self.create_items()
        else:
            self.update_items()

    def make_item(self, price_list):
        return EventTypePriceListItem(
            price_list=price_list,
            template=self,
            **{field: getattr(self, field) for field in self.template_fields},
        )

    def create_items(self):
        """Creates new event types for connected price lists."""
        items_for_create = []

        for price_list in self.template.price_lists.all():
            items_for_create.append(self.make_item(price_list))

        if items_for_create:
            EventTypePriceListItem.objects.bulk_create(items_for_create)

    def update_items(self):
        """Updates all connected event types."""
        items_for_update = []
        items = self.event_prices.select_related("event_type")

        for item in items:
            for field in self.template_fields:
                setattr(item, field, getattr(self, field))
            items_for_update.append(item)

        if items_for_update:
            items.bulk_update(items_for_update, fields=self.template_fields)


class EventTypePriceListItem(EventTypeTaxPercentage, GeneralPriceListItem):
    template = models.ForeignKey(
        EventTypePriceListTemplateItem,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="event_prices",
    )

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

    def __str__(self):
        return f"{self.price}:{self.event_type.name}"


class UserGroupItemTaxPercentage:
    """Mixin class for calculating user group tax percentage."""

    @property
    def tax_percentage(self):
        return self.user_group.tax_percentage


class UserGroupPriceListTemplateItem(UserGroupItemTaxPercentage, GeneralPriceListItem):
    template = models.ForeignKey(
        PriceListTemplate,
        related_name="usergroup_prices",
        on_delete=models.CASCADE,
        verbose_name=_("template"),
    )
    user_group = models.ForeignKey(
        UserGroup,
        related_name="pricelist_template_items",
        on_delete=models.CASCADE,
        verbose_name=_("user group"),
    )

    template_fields = [
        "user_group",
        "price",
        "price_period",
        "price_type",
    ]

    class Meta:
        verbose_name = _("User group price template")
        verbose_name_plural = _("User group price templates")

    def __str__(self):
        return f"{self.price}:{self.user_group.name}"

    def save(self, **kwargs):
        is_new = self.pk is None
        super().save(**kwargs)
        if is_new:
            self.create_items()
        else:
            self.update_items()

    def make_item(self, price_list):
        return UserGroupPriceListItem(
            price_list=price_list,
            template=self,
            **{field: getattr(self, field) for field in self.template_fields},
        )

    def create_items(self):
        """Creates new user groups for connected price lists."""
        items_for_create = []

        for price_list in self.template.price_lists.all():
            items_for_create.append(self.make_item(price_list))

        if items_for_create:
            UserGroupPriceListItem.objects.bulk_create(items_for_create)

    def update_items(self):
        """Updates all connected user groups."""
        items_for_update = []

        items = self.usergroup_prices.select_related("user_group")

        for item in items:
            for field in self.template_fields:
                setattr(item, field, getattr(self, field))
            items_for_update.append(item)

        if items_for_update:
            items.bulk_update(items_for_update, fields=self.template_fields)


class UserGroupPriceListItem(UserGroupItemTaxPercentage, GeneralPriceListItem):
    template = models.ForeignKey(
        UserGroupPriceListTemplateItem,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="usergroup_prices",
    )

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

    def __str__(self):
        return f"{self.price}:{self.user_group.name}"


@rounded
def _pre_tax_to_after_tax(pretax_price, tax_percentage):
    return convert_pretax_to_aftertax(pretax_price, tax_percentage)
