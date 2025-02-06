from django.contrib import messages
from django.core.exceptions import FieldDoesNotExist
from django.db.models import Q
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
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
            state=self.model.CONFIRMED,
            invoice_approved_at__isnull=False,
            resource__in=managed_resources
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


def mark_reservation_ready_for_invoicing(request, reservation_id):
    """
    Mark the reservation as ready for invoicing by
    setting invoice_marked_ready_at.

    Also checks that the reservation has the data needed for
    generating the invoice XML for SAP.
    """
    reservation = get_object_or_404(Reservation, id=reservation_id)

    # Check we have the data needed for the XML
    valid, invalid_fields = validate_data_required_by_sap(reservation)

    if valid:
        reservation.invoice_marked_ready_at = timezone.now()
        reservation.save()
    else:
        messages.error(
            request, _("Missing information required by SAP: {}").format(invalid_fields)
        )

    return HttpResponseRedirect(request.META.get("HTTP_REFERER"))


def validate_data_required_by_sap(reservation):
    invalid_fields = []
    unit = reservation.resource.unit
    required_reservation_fields = [
        "reserver_id",
        "company",
        "company_address_street",
        "company_address_city",
        "company_address_zip",
    ]
    required_unit_fields = [
        "sap_cost_center_code",
        "sap_sales_organization",
        "sap_unit_id",
        "sap_income_account",
    ]

    for field in required_reservation_fields:
        if not getattr(reservation, field):
            invalid_fields.append(field)

    for field in required_unit_fields:
        if not getattr(unit, field):
            invalid_fields.append(field)

    if invalid_fields:
        return False, invalid_fields
    return True, invalid_fields
