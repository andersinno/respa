from django.db.models import FieldDoesNotExist
from django.http import HttpResponseRedirect
from django.urls import reverse_lazy, reverse
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from respa_admin.views.base import ExtraContextMixin
from respa_pricing.forms import (
    EventTypePriceListItemFormset,
    PriceListForm,
    UserGroupPriceListItemFormset,
)
from respa_pricing.models import PriceList


class PriceListView(ExtraContextMixin, ListView):
    model = PriceList
    paginate_by = 10
    context_object_name = "price_lists"
    template_name = "respa_admin/page_price_lists.html"

    def get(self, request, *args, **kwargs):
        get_params = request.GET
        self.search_query = get_params.get("search_query")
        self.order_by = get_params.get("order_by", "name")
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data()
        context["search_query"] = self.search_query or ""
        context["order_by"] = self.order_by
        return context

    def get_queryset(self):
        qs = PriceList.objects.modifiable_by(self.request.user)

        if self.search_query:
            qs = qs.filter(name__icontains=self.search_query)
        if self.order_by:
            order_by_param = self.order_by.strip("-")
            try:
                if PriceList._meta.get_field(order_by_param):
                    qs = qs.order_by(self.order_by)
            except FieldDoesNotExist:
                pass
        return qs


class PriceListCreateView(ExtraContextMixin, CreateView):
    model = PriceList
    pk_url_kwarg = "price_list_id"
    form_class = PriceListForm
    template_name = "respa_admin/price_lists/price_list_form.html"

    def get_success_url(self):
        return reverse(
            "respa_admin:edit-price-list", kwargs={"price_list_id": self.object.pk}
        )

    def get(self, request, *args, **kwargs):
        self.object = None
        form_class = self.get_form_class()
        form = self.get_form(form_class)
        user_group_item_formset = UserGroupPriceListItemFormset(instance=self.object)
        event_type_item_formset = EventTypePriceListItemFormset(instance=self.object)

        return self.render_to_response(
            self.get_context_data(
                form=form,
                user_group_item_formset=user_group_item_formset,
                event_type_item_formset=event_type_item_formset,
            )
        )

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        resource_id = self.request.GET.get("resource_id")
        form.fields["resource"].queryset = form.fields[
            "resource"
        ].queryset.modifiable_by(self.request.user)
        form.fields["resource"].initial = resource_id
        return form

    def get_queryset(self):
        qs = super().get_queryset()
        return qs.modifiable_by(self.request.user)

    def post(self, request, *args, **kwargs):
        self.object = None
        form_class = self.get_form_class()
        form = self.get_form(form_class)
        user_group_item_formset = UserGroupPriceListItemFormset(self.request.POST)
        event_type_item_formset = EventTypePriceListItemFormset(self.request.POST)

        if (
            form.is_valid()
            and user_group_item_formset.is_valid()
            and event_type_item_formset.is_valid()
        ):
            return self.form_valid(
                form,
                user_group_item_formset,
                event_type_item_formset,
            )
        else:
            return self.form_invalid(
                form, user_group_item_formset, event_type_item_formset
            )

    def form_valid(self, form, user_group_item_formset, event_type_item_formset):
        self.object = form.save()
        user_group_item_formset.instance = self.object
        user_group_item_formset.save()
        event_type_item_formset.instance = self.object
        event_type_item_formset.save()
        return HttpResponseRedirect(self.get_success_url())

    def form_invalid(self, form, user_group_item_formset, event_type_item_formset):
        return self.render_to_response(
            self.get_context_data(
                form=form,
                user_group_item_formset=user_group_item_formset,
                event_type_item_formset=event_type_item_formset,
            )
        )


class PriceListEditView(ExtraContextMixin, UpdateView):
    model = PriceList
    pk_url_kwarg = "price_list_id"
    form_class = PriceListForm
    template_name = "respa_admin/price_lists/price_list_form.html"

    def get_success_url(self):
        return reverse(
            "respa_admin:edit-price-list", kwargs={"price_list_id": self.object.pk}
        )

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        form_class = self.get_form_class()
        form = self.get_form(form_class)
        user_group_item_formset = UserGroupPriceListItemFormset(instance=self.object)
        event_type_item_formset = EventTypePriceListItemFormset(instance=self.object)

        return self.render_to_response(
            self.get_context_data(
                form=form,
                user_group_item_formset=user_group_item_formset,
                event_type_item_formset=event_type_item_formset,
            )
        )

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields["resource"].queryset = form.fields[
            "resource"
        ].queryset.modifiable_by(self.request.user)
        return form

    def get_queryset(self):
        qs = super().get_queryset()
        return qs.modifiable_by(self.request.user)

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        form_class = self.get_form_class()
        form = self.get_form(form_class)
        user_group_item_formset = UserGroupPriceListItemFormset(
            self.request.POST, instance=self.object
        )
        event_type_item_formset = EventTypePriceListItemFormset(
            self.request.POST, instance=self.object
        )

        if (
            form.is_valid()
            and user_group_item_formset.is_valid()
            and event_type_item_formset.is_valid()
        ):
            return self.form_valid(
                form,
                user_group_item_formset,
                event_type_item_formset,
            )
        else:
            return self.form_invalid(
                form, user_group_item_formset, event_type_item_formset
            )

    def form_valid(self, form, user_group_item_formset, event_type_item_formset):
        self.object = form.save()
        user_group_item_formset.instance = self.object
        user_group_item_formset.save()
        event_type_item_formset.instance = self.object
        event_type_item_formset.save()
        return HttpResponseRedirect(self.get_success_url())

    def form_invalid(self, form, user_group_item_formset, event_type_item_formset):
        return self.render_to_response(
            self.get_context_data(
                form=form,
                user_group_item_formset=user_group_item_formset,
                event_type_item_formset=event_type_item_formset,
            )
        )


class PriceListDeleteView(ExtraContextMixin, DeleteView):
    """A view to remove a price list"""

    model = PriceList
    template_name = "respa_admin/price_lists/price_list_confirm_delete.html"
    pk_url_kwarg = "price_list_id"
    success_url = reverse_lazy("respa_admin:price-list")

    def get_queryset(self):
        qs = super().get_queryset()
        return qs.modifiable_by(self.request.user)
