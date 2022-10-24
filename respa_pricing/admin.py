from django.contrib import admin
from django.conf import settings
from django.contrib.admin import site as admin_site
from modeltranslation.admin import TranslationAdmin

from resources.admin.base import CommonExcludeMixin, PopulateCreatedAndModifiedMixin
from .models import Event, PriceList, EventPriceListItem, UserGroup, UserGroupPriceListItem


class UserGroupAdmin(PopulateCreatedAndModifiedMixin, CommonExcludeMixin, admin.ModelAdmin):
    pass


class EventAdmin(PopulateCreatedAndModifiedMixin, CommonExcludeMixin, admin.ModelAdmin):
    pass


class UserGroupPriceListItemAdmin(PopulateCreatedAndModifiedMixin, CommonExcludeMixin, admin.ModelAdmin):
    fields = (
        'user_group',
        'price',
        'tax_percentage',
        'price_type',
        'price_period',
        'price_list',
    )


class EventPriceListItemAdmin(PopulateCreatedAndModifiedMixin, CommonExcludeMixin, admin.ModelAdmin):
    fields = (
        'event',
        'price',
        'tax_percentage',
        'price_type',
        'price_period',
        'price_list',
    )


class PriceListAdmin(admin.ModelAdmin):
    pass


if settings.RESPA_PAYMENTS_ENABLED:
    admin_site.register(Event, EventAdmin)
    admin.site.register(UserGroup, UserGroupAdmin)
    admin.site.register(EventPriceListItem, EventPriceListItemAdmin)
    admin.site.register(UserGroupPriceListItem, UserGroupPriceListItemAdmin)
    admin.site.register(PriceList, PriceListAdmin)
