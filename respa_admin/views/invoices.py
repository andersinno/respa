from django.db.models import FieldDoesNotExist
from django.views.generic import ListView

from payments.models import Invoice
from respa_admin.views.base import ExtraContextMixin

class InvoiceListView(ExtraContextMixin, ListView):
    model = Invoice
    paginate_by = 10
    context_object_name = "invoices"
    template_name = "respa_admin/page_invoices.html"

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
        qs = Invoice.objects.all()

        if self.order_by:
            order_by_param = self.order_by.strip("-")
            try:
                if Invoice._meta.get_field(order_by_param):
                    qs = qs.order_by(self.order_by)
            except FieldDoesNotExist:
                pass
        return qs
