from django.db.models import FieldDoesNotExist, Q
from django.views.generic import ListView

from resources.models import Reservation, Resource
from respa_admin.views.base import ExtraContextMixin


class InvoiceableReservationListView(ExtraContextMixin, ListView):
    model = Reservation
    paginate_by = 10
    context_object_name = "reservations"
    template_name = "respa_admin/page_invoiceable_reservations.html"

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
        managed_resources = Resource.objects.modifiable_by(self.request.user)
        qs = Reservation.objects.filter(
            invoice_approved_at__isnull=False, resource__in=managed_resources
        ).select_related("order", "resource")

        if self.search_query:
            qs = qs.filter(
                Q(resource__name__icontains=self.search_query)
                | Q(company__icontains=self.search_query)
                | Q(reserver_id__icontains=self.search_query)
            )
        if self.order_by:
            order_by_param = self.order_by.strip("-")
            try:
                if Reservation._meta.get_field(order_by_param):
                    qs = qs.order_by(self.order_by)
            except FieldDoesNotExist:
                pass
        return qs
