from django.views.generic import CreateView, ListView

from respa_pricing.models import PriceList
from respa_admin.forms import PriceListForm

class PriceListView(ListView):
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


class PriceListEditView(CreateView):
    http_method_names = ['get', 'post']
    model = PriceList
    pk_url_kwarg = 'price_list_id'
    form_class = PriceListForm
    template_name = 'respa_admin/price_lists/create_price_list.html'
