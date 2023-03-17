from django.core.exceptions import PermissionDenied
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from respa_pricing.models import PriceList
from respa_admin.forms import PriceListForm
from respa_admin.views.base import ExtraContextMixin


class PriceListView(ExtraContextMixin, ListView):
    model = PriceList
    paginate_by = 10
    context_object_name = 'price_lists'
    template_name = 'respa_admin/page_price_lists.html'

    def get(self, request, *args, **kwargs):
        get_params = request.GET
        self.search_query = get_params.get('search_query')
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data()
        context['search_query'] = self.search_query or ''
        return context

    def get_queryset(self):
        qs = PriceList.objects.all()

        if self.search_query:
            qs = qs.filter(name__icontains=self.search_query)
        return qs


class PriceListCreateView(ExtraContextMixin, CreateView):
    model = PriceList
    pk_url_kwarg = 'price_list_id'
    form_class = PriceListForm
    template_name = 'respa_admin/price_lists/price_list_form.html'


class PriceListEditView(ExtraContextMixin, UpdateView):
    model = PriceList
    pk_url_kwarg = 'price_list_id'
    form_class = PriceListForm
    template_name = 'respa_admin/price_lists/price_list_form.html'


class PriceListDeleteView(ExtraContextMixin, DeleteView):
    """ A view to remove a price list """

    model = PriceList
    template_name = "respa_admin/price_lists/price_list_confirm_delete.html"
    pk_url_kwarg = "price_list_id"
    success_url = reverse_lazy("respa_admin:price-list")

    def get_object(self, *args, **kwargs):
        """ Check that the user has permissions to the object before passing to the view. """
        price_list = super().get_object(*args, **kwargs)
        if True:
            # TODO
            return price_list
        else:
            raise PermissionDenied()
