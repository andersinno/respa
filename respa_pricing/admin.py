from django.conf import settings
from django.contrib import admin
from django.contrib.admin import site as admin_site
from django.utils.timezone import now
from django.utils.translation import ugettext_lazy as _
from modeltranslation.admin import TranslationAdmin

from payments.models import Product
from resources.admin.base import CommonExcludeMixin, PopulateCreatedAndModifiedMixin

from .forms import EventTypePriceListItemFormset
from .forms import PriceListForm as BasePriceListForm
from .forms import UserGroupPriceListItemFormset
from .models import (
    EventType,
    EventTypePriceListItem,
    EventTypePriceListTemplateItem,
    PricedProduct,
    PriceList,
    PriceListTemplate,
    UserGroup,
    UserGroupPriceListItem,
    UserGroupPriceListTemplateItem,
)


class UserGroupAdmin(
    PopulateCreatedAndModifiedMixin, CommonExcludeMixin, TranslationAdmin
):
    pass


class EventTypeAdmin(
    PopulateCreatedAndModifiedMixin, CommonExcludeMixin, TranslationAdmin
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
        "get_pretax_price",
        "price_type",
        "price_period",
        "price_list",
    )
    extra = 0
    formset = EventTypePriceListItemFormset


class PriceListForm(BasePriceListForm):
    class Meta(BasePriceListForm.Meta):
        fields = BasePriceListForm.Meta.fields + ("include_other_event_type_option",)


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


class UserGroupPriceListTemplateItemInline(
    PreTaxMixin,
    PopulateCreatedAndModifiedMixin,
    CommonExcludeMixin,
    admin.TabularInline,
):
    model = UserGroupPriceListTemplateItem
    fields = (
        "user_group",
        "price",
        "get_pretax_price",
        "price_type",
        "price_period",
    )
    extra = 0
    formset = UserGroupPriceListItemFormset
    min_num = 1


class EventTypePriceListTemplateItemInline(
    PreTaxMixin,
    PopulateCreatedAndModifiedMixin,
    CommonExcludeMixin,
    admin.TabularInline,
):
    model = EventTypePriceListTemplateItem
    fields = (
        "event_type",
        "price",
        "get_pretax_price",
        "price_type",
        "price_period",
    )
    extra = 0
    formset = EventTypePriceListItemFormset


class PriceListTemplateAdmin(admin.ModelAdmin):
    inlines = [
        UserGroupPriceListTemplateItemInline,
        EventTypePriceListTemplateItemInline,
    ]


if settings.RESPA_PAYMENTS_ENABLED:
    admin_site.register(EventType, EventTypeAdmin)
    admin.site.register(UserGroup, UserGroupAdmin)
    admin.site.register(PriceList, PriceListAdmin)
    admin.site.register(PriceListTemplate, PriceListTemplateAdmin)
