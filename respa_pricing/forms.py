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
    resource = forms.ModelChoiceField(
        queryset=None, required=False, label=_("Resource")
    )

    def __init__(self, *args, **kwargs):
        """
        Allow selecting resources that are not linked to any other price list.
        Initially select the resource linked to the price list instance.
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
            if linked_resources:
                self.fields["resource"].initial = linked_resources.first()

        self.fields["resource"].queryset = queryset.distinct().order_by("name")

    def save(self, commit=True):
        """
        Create or archive the product (and handle the priced product)
        based on the selected resource.
        """
        saved_form = super().save(commit=commit)
        current_resource = None
        selected_resource = self.cleaned_data["resource"]

        if self.instance.pk and hasattr(self.instance, "priced_product"):
            current_resource = self.instance.priced_product.product.resources.first()

        if commit:
            if current_resource and selected_resource != current_resource:
                # Archive existing products linked to the price list
                self.instance.priced_product.product.archived_at = now()
                self.instance.priced_product.product.save()
                self.instance.priced_product.delete()

            if selected_resource and selected_resource != current_resource:
                # Create new product
                prod = Product.objects.create(name=selected_resource.name)
                prod.resources.add(selected_resource)
                PricedProduct.objects.create(product=prod, price_list=self.instance)

        return saved_form

    class Meta:
        model = PriceList
        fields = ("name", "resource", "include_other_event_type_option",)


class AtLeastOneRequiredInlineFormSet(forms.models.BaseInlineFormSet):
    def clean(self):
        """Check that at least one item has been entered."""
        super(AtLeastOneRequiredInlineFormSet, self).clean()
        if any(self.errors):
            return
        if not any(
            cleaned_data and not cleaned_data.get("DELETE", False)
            for cleaned_data in self.cleaned_data
        ):
            raise forms.ValidationError(_("At least one item required."))


UserGroupPriceListItemFormset = forms.inlineformset_factory(
    PriceList,
    UserGroupPriceListItem,
    formset=AtLeastOneRequiredInlineFormSet,
    fields=("user_group", "price", "price_period", "price_type"),
    can_delete=True,
    min_num=1,
    extra=0,
)

EventTypePriceListItemFormset = forms.inlineformset_factory(
    PriceList,
    EventTypePriceListItem,
    fields=("event_type", "price", "price_period", "price_type"),
    can_delete=True,
    extra=0,
)
