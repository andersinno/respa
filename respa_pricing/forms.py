from django import forms

from django.utils.timezone import now
from django.utils.translation import ugettext_lazy as _

from payments.models import Product, Resource

from .models import (
    PriceList,
    PricedProduct,
    EventTypePriceListItem,
    UserGroupPriceListItem,
)


class PriceListForm(forms.ModelForm):
    resources = forms.ModelMultipleChoiceField(
        queryset=None, required=False, label=_("Resources")
    )

    def __init__(self, *args, **kwargs):
        """
        Allow selecting resources that are not linked to any other price list.
        Initially select the resources linked to the price list instance.
        """
        super().__init__(*args, **kwargs)

        # Resources not linked to any price list
        queryset = Resource.objects.exclude(
            products__in=Product.objects.filter(pricedproduct__price_list__isnull=False)
        )

        if self.instance.pk:
            # Resources linked to this price list
            linked_resources = Resource.objects.filter(
                products__pricedproduct__price_list=self.instance
            )
            queryset = queryset | linked_resources
            self.fields["resources"].initial = linked_resources

        self.fields["resources"].queryset = queryset.distinct().order_by("name")

    def save(self, commit=True):
        """
        Create or archive the products (and handle the priced products)
        based on the selected resources.
        """
        saved_form = super().save(commit=False)
        selected_resources = self.cleaned_data["resources"]
        priced_prod_ids = []
        saved_form.save()

        for resource in selected_resources:
            # Archive existing products linked to the resource
            existing_products = Product.objects.current().filter(
                resources__in=[resource]
            )
            existing_products.update(archived_at=now())
            existing_products_ids = existing_products.values_list("id")
            PricedProduct.objects.filter(pk__in=existing_products_ids).delete()

            # Create new product
            prod = Product.objects.create(name=resource.name)
            prod.resources.add(resource)
            priced_prod = PricedProduct.objects.create(
                product=prod, price_list=self.instance
            )
            priced_prod_ids.append(priced_prod.pk)

        if self.instance.pk:
            # Archive products that are not selected anymore
            Product.objects.current().exclude(
                pricedproduct__pk__in=priced_prod_ids
            ).filter(pricedproduct__price_list=self.instance).update(archived_at=now())
            self.instance.priced_products.all().exclude(pk__in=priced_prod_ids).delete()

        return saved_form

    class Meta:
        model = PriceList
        fields = ("name",)

UserGroupPriceListItemFormset = forms.inlineformset_factory(
    PriceList,
    UserGroupPriceListItem,
    fields=("user_group", "price", "tax_percentage", "price_period", "price_type"),
    extra=1,
)

EventTypePriceListItemFormset = forms.inlineformset_factory(
    PriceList,
    EventTypePriceListItem,
    fields=("event_type", "price", "tax_percentage", "price_period", "price_type"),
    extra=1,
)
