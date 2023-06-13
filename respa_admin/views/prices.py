from django.contrib import messages
from django.db.models import FieldDoesNotExist
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse, reverse_lazy
from django.utils.functional import cached_property
from django.utils.translation import gettext as _
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from respa_admin.views.base import ExtraContextMixin
from respa_pricing.forms import (
    EventTypePriceListItemFormset,
    EventTypePriceListTemplateItemFormset,
    PriceListForm,
    UserGroupPriceListItemFormset,
    UserGroupPriceListTemplateItemFormset,
)
from respa_pricing.models import PriceList, PriceListTemplate


class PriceListTemplateView(ExtraContextMixin, ListView):
    model = PriceListTemplate
    paginate_by = 10
    context_object_name = "price_list_templates"
    template_name = "respa_admin/page_price_list_templates.html"

    @cached_property
    def search_query(self):
        return self.request.GET.get("search_query", "")

    def get_context_data(self, **kwargs):
        return {
            **super().get_context_data(**kwargs),
            "search_query": self.search_query,
        }

    def get_queryset(self):
        qs = PriceListTemplate.objects.all()
        if self.search_query:
            qs = qs.filter(name__icontains=self.search_query)
        return qs


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
        qs = PriceList.objects.modifiable_by(self.request.user).select_related(
            "template"
        )

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


class PriceListFormMixin:
    model = PriceList
    form_class = PriceListForm
    pk_url_kwarg = "price_list_id"
    template_name = "respa_admin/price_lists/price_list_form.html"

    def get_success_url(self):
        return reverse(
            "respa_admin:edit-price-list", kwargs={"price_list_id": self.object.pk}
        )


class PriceListCreateView(ExtraContextMixin, PriceListFormMixin, CreateView):
    @cached_property
    def price_list_template(self):
        if "template_id" in self.kwargs:
            return get_object_or_404(PriceListTemplate, pk=self.kwargs["template_id"])
        return None

    def get(self, request, *args, **kwargs):
        self.object = None
        form_class = self.get_form_class()
        form = self.get_form(form_class)

        if self.price_list_template:
            user_group_item_formset = _make_formset_readonly(
                UserGroupPriceListTemplateItemFormset(instance=self.price_list_template)
            )

            event_type_item_formset = _make_formset_readonly(
                EventTypePriceListTemplateItemFormset(instance=self.price_list_template)
            )

        else:
            user_group_item_formset = UserGroupPriceListItemFormset(
                instance=self.object
            )
            event_type_item_formset = EventTypePriceListItemFormset(
                instance=self.object
            )

        return self.render_to_response(
            self.get_context_data(
                form=form,
                user_group_item_formset=user_group_item_formset,
                event_type_item_formset=event_type_item_formset,
                price_list_template=self.price_list_template,
            )
        )

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        resource_id = self.request.GET.get("resource_id")
        form.fields["resource"].queryset = form.fields[
            "resource"
        ].queryset.modifiable_by(self.request.user)
        form.fields["resource"].initial = resource_id
        if self.price_list_template:
            return _make_form_readonly(form, self.price_list_template.template_fields)
        return form

    def get_queryset(self):
        return super().get_queryset().modifiable_by(self.request.user)

    def post(self, request, *args, **kwargs):
        self.object = None
        form_class = self.get_form_class()
        form = self.get_form(form_class)
        forms_are_valid = form.is_valid()

        if self.price_list_template:
            if forms_are_valid:
                user_group_item_formset, event_type_item_formset = None, None
            else:
                user_group_item_formset = _make_formset_readonly(
                    UserGroupPriceListTemplateItemFormset(
                        instance=self.price_list_template
                    )
                )

                event_type_item_formset = _make_formset_readonly(
                    EventTypePriceListTemplateItemFormset(
                        instance=self.price_list_template
                    )
                )

        else:
            user_group_item_formset = UserGroupPriceListItemFormset(
                self.request.POST, save_as_new=True
            )
            event_type_item_formset = EventTypePriceListItemFormset(
                self.request.POST, save_as_new=True
            )
            forms_are_valid = (
                forms_are_valid
                and user_group_item_formset.is_valid()
                and event_type_item_formset.is_valid()
            )

        if forms_are_valid:
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
        if self.price_list_template:
            self.object = self.price_list_template.add_price_list(self.object)
        else:
            user_group_item_formset.instance = self.object
            user_group_item_formset.save()
            event_type_item_formset.instance = self.object
            event_type_item_formset.save()

        messages.success(self.request, _("Price list saved"))

        return HttpResponseRedirect(self.get_success_url())

    def form_invalid(self, form, user_group_item_formset, event_type_item_formset):
        return self.render_to_response(
            self.get_context_data(
                form=form,
                user_group_item_formset=user_group_item_formset,
                event_type_item_formset=event_type_item_formset,
                price_list_template=self.price_list_template,
            )
        )


class PriceListEditView(ExtraContextMixin, PriceListFormMixin, UpdateView):
    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        form_class = self.get_form_class()
        form = self.get_form(form_class)

        user_group_item_formset = UserGroupPriceListItemFormset(instance=self.object)
        event_type_item_formset = EventTypePriceListItemFormset(instance=self.object)

        if self.object.template:
            user_group_item_formset = _make_formset_readonly(user_group_item_formset)
            event_type_item_formset = _make_formset_readonly(event_type_item_formset)

        return self.render_to_response(
            self.get_context_data(
                form=form,
                user_group_item_formset=user_group_item_formset,
                event_type_item_formset=event_type_item_formset,
                price_list_template=self.object.template,
            )
        )

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields["resource"].queryset = form.fields[
            "resource"
        ].queryset.modifiable_by(self.request.user)
        if self.object.template:
            form = _make_form_readonly(form, self.object.template.template_fields)
        return form

    def get_queryset(self):
        return super().get_queryset().modifiable_by(self.request.user)

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        form_class = self.get_form_class()
        form = self.get_form(form_class)

        forms_are_valid = form.is_valid()

        if self.object.template:
            if forms_are_valid:
                user_group_item_formset, event_type_item_formset = None, None
            else:
                user_group_item_formset = _make_formset_readonly(
                    UserGroupPriceListItemFormset(instance=self.object)
                )
                event_type_item_formset = _make_formset_readonly(
                    EventTypePriceListItemFormset(instance=self.object)
                )

        else:
            user_group_item_formset = UserGroupPriceListItemFormset(
                self.request.POST, instance=self.object
            )
            event_type_item_formset = EventTypePriceListItemFormset(
                self.request.POST, instance=self.object
            )

            forms_are_valid = (
                forms_are_valid
                and user_group_item_formset.is_valid()
                and event_type_item_formset.is_valid()
            )

        if forms_are_valid:
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
        if not self.object.template:
            user_group_item_formset.instance = self.object
            user_group_item_formset.save()
            event_type_item_formset.instance = self.object
            event_type_item_formset.save()

        messages.success(self.request, _("Price list saved"))

        return HttpResponseRedirect(self.get_success_url())

    def form_invalid(self, form, user_group_item_formset, event_type_item_formset):
        return self.render_to_response(
            self.get_context_data(
                form=form,
                user_group_item_formset=user_group_item_formset,
                event_type_item_formset=event_type_item_formset,
                price_list_template=self.object.template,
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


class PriceListCopyView(PriceListCreateView):
    def get(self, request, *args, **kwargs):
        self.object = None
        original_object = get_object_or_404(
            PriceList,
            template__isnull=True,
            pk=self.kwargs.get("price_list_id"),
        )

        form_class = self.get_form_class()
        form = self.get_form(form_class)

        user_group_item_formset = UserGroupPriceListItemFormset(
            instance=original_object
        )
        event_type_item_formset = EventTypePriceListItemFormset(
            instance=original_object
        )

        return self.render_to_response(
            self.get_context_data(
                form=form,
                user_group_item_formset=user_group_item_formset,
                event_type_item_formset=event_type_item_formset,
            )
        )


def _make_form_readonly(form, fields=None):
    fields = fields or form.fields
    for field in fields:
        if field in form.fields:
            form.fields[field].widget.attrs.update(
                {
                    "disabled": True,
                    "readonly": True,
                }
            )
    return form


def _make_formset_readonly(formset, fields=None):
    for form in formset.forms:
        _make_form_readonly(form, fields)
    return formset
