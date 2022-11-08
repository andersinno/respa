from django.contrib import admin
from django.conf import settings
from django.contrib.admin import site as admin_site
from django.db.models import Q
from django import forms

from resources.admin.base import CommonExcludeMixin, PopulateCreatedAndModifiedMixin
from .models import Event, PriceList, EventPriceListItem, UserGroup, UserGroupPriceListItem


class UserGroupAdmin(PopulateCreatedAndModifiedMixin, CommonExcludeMixin, admin.ModelAdmin):
    pass


class EventAdmin(PopulateCreatedAndModifiedMixin, CommonExcludeMixin, admin.ModelAdmin):
    pass


class UserGroupPriceListItemForm(forms.ModelForm):
    pre_tax_price = forms.DecimalField()

    class Meta:
        model = UserGroupPriceListItem
        fields = (
            'user_group',
            'price',
            'tax_percentage',
            'price_type',
            'price_period',
            'price_list',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        un_used_user_groups = UserGroup.objects.filter(pricelist_items=None)
        if not self.instance.id:
            self.fields['user_group'].queryset = un_used_user_groups
        else:
            self.fields['user_group'].queryset = UserGroup.objects.filter(
                Q(pricelist_items=None) | Q(pricelist_items=self.instance.id)
            )


class PreTaxMixin:
    readonly_fields = ('get_pretax_price',)

    def get_pretax_price(self, obj):
        if obj.id:
            return obj.get_pretax_price()
        return 0

    get_pretax_price.short_description = 'Price before tax'


class UserGroupPriceListItemAdmin(PreTaxMixin, PopulateCreatedAndModifiedMixin, CommonExcludeMixin, admin.ModelAdmin):
    form = UserGroupPriceListItemForm
    fields = (
        'user_group',
        'price',
        'tax_percentage',
        'get_pretax_price',
        'price_type',
        'price_period',
        'price_list',
    )


class EventPriceListItemAdmin(PreTaxMixin, PopulateCreatedAndModifiedMixin, CommonExcludeMixin, admin.ModelAdmin):
    fields = (
        'event',
        'price',
        'tax_percentage',
        'get_pretax_price',
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
