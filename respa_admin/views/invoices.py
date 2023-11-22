from django.contrib import messages
from django.db.models import FieldDoesNotExist
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.translation import ugettext_lazy as _
from django.views.generic import DetailView, ListView

from payments.models import Invoice
from payments.sap_invoices import generate_sales_order
from resources.models import Reservation
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


class InvoiceDetailView(ExtraContextMixin, DetailView):
    model = Invoice
    template_name = "respa_admin/invoices/_invoice_detail.html"


def generate_invoice_xml(request, invoice_id):
    """
    Regenerate the invoice XML for SAP.
    """
    invoice = get_object_or_404(Invoice, id=invoice_id)
    reservations = Reservation.objects.filter(order__invoice=invoice)

    xml = generate_sales_order(reservations)

    if xml:
        now = timezone.now()
        invoice.xml = xml
        invoice.xml_generated_at = now
        invoice.save()
        reservations.update(invoice_generated_at=now)
        messages.success(request, _("XML generated succesfully"))
    else:
        messages.error(request, _("Failed to generate the XML"))

    next = reverse_lazy("respa_admin:invoice-detail", kwargs={"pk": invoice_id})
    return HttpResponseRedirect(next)
