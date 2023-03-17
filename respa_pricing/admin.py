from django.contrib import admin
from django.conf import settings
from django.contrib.admin import site as admin_site
from django.utils.translation import ugettext_lazy as _

from resources.admin.base import CommonExcludeMixin, PopulateCreatedAndModifiedMixin
from .forms import PriceListForm
from .models import (
    EventType,
    PriceList,
    EventTypePriceListItem,
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
    # form = UserGroupPriceListItemForm
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


class PriceListAdmin(admin.ModelAdmin):
    form = PriceListForm
    inlines = [
        UserGroupPriceListItemInline,
        EventTypePriceListItemInline,
    ]


if settings.RESPA_PAYMENTS_ENABLED:
    admin_site.register(EventType, EventTypeAdmin)
    admin.site.register(UserGroup, UserGroupAdmin)
    admin.site.register(PriceList, PriceListAdmin)
