from django.contrib import admin
from django.conf import settings
from django.contrib.admin import site as admin_site
from django.utils.timezone import now
from django.utils.translation import ugettext_lazy as _

from payments.models import Product
from resources.admin.base import CommonExcludeMixin, PopulateCreatedAndModifiedMixin
from .forms import (
    PriceListForm,
    UserGroupPriceListItemFormset,
    EventTypePriceListItemFormset,
)
from .models import (
    EventType,
    PriceList,
    PricedProduct,
    EventTypePriceListItem,
    RespaPaymentTerm,
    UserGroup,
    UserGroupPriceListItem,
)


class UserGroupAdmin(
    PopulateCreatedAndModifiedMixin, CommonExcludeMixin, admin.ModelAdmin
):
    pass


class EventTypeAdmin(
    PopulateCreatedAndModifiedMixin, CommonExcludeMixin, admin.ModelAdmin
):
    pass


class PreTaxMixin:
    readonly_fields = ("get_pretax_price",)

    def get_pretax_price(self, obj):
        if obj.id:
            return obj.get_pretax_price()
        return 0

    get_pretax_price.short_description = _("Price before tax")


class UserGroupPriceListItemInline(
    PreTaxMixin,
    PopulateCreatedAndModifiedMixin,
    CommonExcludeMixin,
    admin.TabularInline,
):
    model = UserGroupPriceListItem
    fields = (
        "user_group",
        "price",
        "tax_percentage",
        "get_pretax_price",
        "price_type",
        "price_period",
        "price_list",
    )
    extra = 0
    formset = UserGroupPriceListItemFormset
    min_num = 1


class EventTypePriceListItemInline(
    PreTaxMixin,
    PopulateCreatedAndModifiedMixin,
    CommonExcludeMixin,
    admin.TabularInline,
):
    model = EventTypePriceListItem
    fields = (
        "event_type",
        "price",
        "tax_percentage",
        "get_pretax_price",
        "price_type",
        "price_period",
        "price_list",
    )
    extra = 0
    formset = EventTypePriceListItemFormset


class PriceListAdmin(admin.ModelAdmin):
    form = PriceListForm
    inlines = [
        UserGroupPriceListItemInline,
        EventTypePriceListItemInline,
    ]

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        current_resource = None
        selected_resource = form.cleaned_data["resource"]

        if change and hasattr(obj, "priced_product"):
            current_resource = obj.priced_product.product.resources.first()

        if current_resource and selected_resource != current_resource:
            # Archive existing products linked to the price list
            obj.priced_product.product.archived_at = now()
            obj.priced_product.product.save()
            obj.priced_product.delete()

        if selected_resource and selected_resource != current_resource:
            # Create new product
            prod = Product.objects.create(name=selected_resource.name)
            prod.resources.add(selected_resource)
            PricedProduct.objects.create(product=prod, price_list=obj)


if settings.RESPA_PAYMENTS_ENABLED:
    admin_site.register(EventType, EventTypeAdmin)
    admin.site.register(UserGroup, UserGroupAdmin)
    admin.site.register(PriceList, PriceListAdmin)
    admin.site.register(RespaPaymentTerm)
