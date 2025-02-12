from django.urls import re_path as unauthorized_url
from django.urls import include

from . import views
from .auth import admin_url as url
from .views.invoices import InvoiceDetailView, InvoiceListView, generate_invoice_xml
from .views.prices import (
    PriceListCopyView,
    PriceListCreateView,
    PriceListDeleteView,
    PriceListEditView,
    PriceListTemplateView,
    PriceListView,
)
from .views.reservations import InvoiceableReservationListView, mark_reservation_ready_for_invoicing
from .views.resources import (
    ManageUserPermissionsListView,
    ManageUserPermissionsSearchView,
    ManageUserPermissionsView,
    ResourceListView,
    SaveResourceView,
    check_cost_center_code,
    copy_resource,
)
from .views.units import UnitEditView, UnitListView

app_name = "respa_admin"
urlpatterns = [
    url(r"^$", ResourceListView.as_view(), name="index"),
    unauthorized_url(r"^login/$", views.LoginView.as_view(), name="login"),
    unauthorized_url(
        r"^login/tunnistamo/$", views.tunnistamo_login, name="tunnistamo-login"
    ),
    unauthorized_url(r"^logout/$", views.logout, name="logout"),
    url(r"^resources/$", ResourceListView.as_view(), name="resources"),
    url(r"^resource/new/$", SaveResourceView.as_view(), name="new-resource"),
    url(
        r"^resource/edit/(?P<resource_id>\w+)/$",
        SaveResourceView.as_view(),
        name="edit-resource",
    ),
    url(r"^resource/copy/(?P<resource_id>\w+)/$", copy_resource, name="copy-resource"),
    url(
        r"^resource/check_cost_center_code/$",
        check_cost_center_code,
        name="check-cost-center-code",
    ),
    url(r"^units/$", UnitListView.as_view(), name="units"),
    url(
        r"^units/edit/(?P<unit_id>[\w\d:]+)/$", UnitEditView.as_view(), name="edit-unit"
    ),
    url(r"^price_list/$", PriceListView.as_view(), name="price-list"),
    url(
        r"^price_list_template/$",
        PriceListTemplateView.as_view(),
        name="price-list-templates",
    ),
    url(
        r"^price_list/edit/(?P<price_list_id>\w+)/$",
        PriceListEditView.as_view(),
        name="edit-price-list",
    ),
    url(
        r"^price_list/delete/(?P<price_list_id>\w+)/$",
        PriceListDeleteView.as_view(),
        name="delete-price-list",
    ),
    url(
        r"^price_list/copy/(?P<price_list_id>\w+)/$",
        PriceListCopyView.as_view(),
        name="copy-price-list",
    ),
    url(r"^price_list/new/$", PriceListCreateView.as_view(), name="new-price-list"),
    url(
        r"^price_list/new/template/(?P<template_id>\w+)/$",
        PriceListCreateView.as_view(),
        name="new-price-list-from-template",
    ),
    url(r"^i18n/$", include("django.conf.urls.i18n"), name="language"),
    url(
        r"^user_management/$",
        ManageUserPermissionsListView.as_view(),
        name="user-management",
    ),
    url(
        r"^user_management/search/$",
        ManageUserPermissionsSearchView.as_view(),
        name="user-management-search",
    ),
    url(
        r"^user_management/(?P<user_id>\w+)/$",
        ManageUserPermissionsView.as_view(),
        name="edit-user",
    ),
    url(
        r"^invoiceable_reservations/$",
        InvoiceableReservationListView.as_view(),
        name="invoiceable-reservations",
    ),
    url(
        r"^invoiceable_reservations/(?P<reservation_id>\w+)/ready/$",
        mark_reservation_ready_for_invoicing,
        name="mark-reservation-ready-for-invoicing",
    ),
    url(
        r"^invoices/$",
        InvoiceListView.as_view(),
        name="invoices",
    ),
    url(
        r"^invoices/(?P<pk>\w+)/$",
        InvoiceDetailView.as_view(),
        name="invoice-detail",
    ),
    url(
        r"^invoices/(?P<invoice_id>\w+)/generate_xml/$",
        generate_invoice_xml,
        name="generate-invoice-xml",
    ),
]
