import arrow
import django_filters
import operator
import uuid
from arrow.parser import ParserError
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import ugettext_lazy as _
from django_filters.rest_framework import DjangoFilterBackend
from functools import reduce
from guardian.core import ObjectPermissionChecker
from munigeo import api as munigeo_api
from rest_framework import (
    exceptions,
    filters,
    permissions,
    renderers,
    serializers,
    viewsets,
)
from rest_framework.authentication import SessionAuthentication, TokenAuthentication
from rest_framework.exceptions import NotAcceptable, ValidationError
from rest_framework.fields import BooleanField, IntegerField
from rest_framework.settings import api_settings as drf_settings

from payments.providers import get_payment_provider
from resources.models import Reservation, ReservationMetadataSet, Resource
from resources.models.reservation import RESERVATION_EXTRA_FIELDS
from resources.models.utils import (
    generate_reservation_csv,
    generate_reservation_xlsx,
    get_object_or_none,
)
from resources.pagination import ReservationPagination
from respa.renderers import ResourcesBrowsableAPIRenderer
from users.utils import get_user_auth_backend

from ..auth import is_general_admin
from .base import (
    DRFFilterBooleanWidget,
    ExtraDataMixin,
    NullableDateTimeField,
    TranslatedModelSerializer,
    register_view,
)

User = get_user_model()

# FIXME: Make this configurable?
USER_ID_ATTRIBUTE = "id"
try:
    User._meta.get_field("uuid")
    USER_ID_ATTRIBUTE = "uuid"
except Exception:
    pass


class UserSerializer(TranslatedModelSerializer):
    display_name = serializers.ReadOnlyField(source="get_display_name")
    email = serializers.ReadOnlyField()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if USER_ID_ATTRIBUTE == "id":
            # id field is read_only by default, that needs to be changed
            # so that the field will be validated
            self.fields["id"] = IntegerField(label="ID")
        else:
            # if the user id attribute isn't id, modify the id field to point to the
            # right attribute. The field needs to be of the right type so that
            # validation works correctly
            model_field_type = type(get_user_model()._meta.get_field(USER_ID_ATTRIBUTE))
            serializer_field = self.serializer_field_mapping[model_field_type]
            self.fields["id"] = serializer_field(source=USER_ID_ATTRIBUTE, label="ID")

    class Meta:
        model = get_user_model()
        fields = ("id", "display_name", "email")


class ReservationSerializer(
    ExtraDataMixin, TranslatedModelSerializer, munigeo_api.GeoModelSerializer
):
    begin = NullableDateTimeField()
    end = NullableDateTimeField()
    user = UserSerializer(required=False)
    is_own = serializers.SerializerMethodField()
    state = serializers.ChoiceField(choices=Reservation.STATE_CHOICES, required=False)
    need_manual_confirmation = serializers.ReadOnlyField()
    user_permissions = serializers.SerializerMethodField()

    class Meta:
        model = Reservation
        fields = [
            "url",
            "id",
            "resource",
            "user",
            "begin",
            "end",
            "comments",
            "is_own",
            "state",
            "need_manual_confirmation",
            "invoice_requested",
            "staff_event",
            "access_code",
            "user_permissions",
            "type",
        ] + list(RESERVATION_EXTRA_FIELDS)
        read_only_fields = list(RESERVATION_EXTRA_FIELDS)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        data = self.get_initial()
        resource = None

        # try to find out the related resource using initial data if that is given
        resource_id = data.get("resource") if data else None
        if resource_id:
            resource = get_object_or_none(Resource, id=resource_id)

        # if that didn't work out use the reservation's old resource if such exists
        if not resource:
            if isinstance(self.instance, Reservation) and isinstance(
                self.instance.resource, Resource
            ):
                resource = self.instance.resource

        # set supported and required extra fields
        if resource:
            cache = self.context.get("reservation_metadata_set_cache")
            # staff events have less requirements
            request_user = self.context["request"].user
            is_staff_event = data.get("staff_event", False)

            required = resource.get_required_reservation_extra_field_names(cache=cache)

            if data.get("invoice_requested", False):
                required = set(required) | {
                    "reserver_id",
                    "company_address",
                    "company_address_street",
                    "company_address_zip",
                    "company_address_city",
                }

            # staff events always have the same set of required fields
            if is_staff_event and resource.can_create_staff_event(request_user):
                required_for_staff = {"reserver_name", "event_description"}

                # billing fields are also required if own use
                if data.get("type", None) == Reservation.TYPE_NORMAL:
                    required_for_staff |= {
                        field
                        for field in (
                            "billing_first_name",
                            "billing_last_name",
                            "billing_email_address",
                        )
                        if field in required
                    }

                required = required_for_staff

            for field_name in required:
                if field_name in self.fields:
                    self.fields[field_name].required = True

            # we don't need to remove a field here if it isn't supported, as it will
            # be read-only and will be more easily removed in to_representation()
            supported = resource.get_supported_reservation_extra_field_names(
                cache=cache
            )

            for field_name in supported:
                if field_name in self.fields:
                    self.fields[field_name].read_only = False

        self.context.update({"resource": resource})

    def get_extra_fields(self, includes, context):
        from .resource import ResourceInlineSerializer

        """ Define extra fields that can be included via query parameters. Method from
        ExtraDataMixin."""
        extra_fields = {}
        if "resource_detail" in includes:
            extra_fields["resource"] = ResourceInlineSerializer(
                read_only=True, context=context
            )
        return extra_fields

    def validate_state(self, value):
        if self.instance and not self.instance.is_new_state_allowed(
            value, self.context["request"].user
        ):
            raise ValidationError(_("Illegal state change"))

        return value

    def validate(self, data):
        reservation = self.instance
        request_user = self.context["request"].user

        # this check is probably only needed for PATCH
        try:
            resource = data["resource"]
        except KeyError:
            resource = reservation.resource

        if not resource.can_make_reservations(request_user):
            raise PermissionDenied(
                _("You are not allowed to make reservations in this resource.")
            )

        is_staff = resource.can_create_staff_event(request_user)

        is_staff_reserver = is_staff and (
            reservation is None
            or reservation.user is None
            or reservation.user == request_user
        )

        can_request_invoice = resource.can_request_invoice and not is_staff_reserver

        if data.get("invoice_requested", False) and not can_request_invoice:
            raise ValidationError(_("You cannot request an invoice for this resource"))

        if data["end"] < timezone.now():
            raise ValidationError(_("You cannot make a reservation in the past"))

        if not resource.can_ignore_opening_hours(request_user):
            reservable_before = resource.get_reservable_before()
            if reservable_before and data["begin"] >= reservable_before:
                raise ValidationError(
                    _(
                        "The resource is reservable only before %(datetime)s"
                        % {"datetime": reservable_before}
                    )
                )
            reservable_after = resource.get_reservable_after()
            if reservable_after and data["begin"] < reservable_after:
                # date falls before the reservable after date. If the number of days
                # difference (based on date rather than datetime) is equal to the min
                # days in advance, then should still be permitted
                is_day_before = (
                    data["begin"].date() - timezone.now().date()
                ).days == resource.get_reservable_min_days_in_advance()

                if not is_day_before:
                    raise ValidationError(
                        _(
                            "The resource is reservable only after %(datetime)s"
                            % {"datetime": reservable_after}
                        )
                    )

        # normal users cannot make reservations for other people
        if not resource.can_create_reservations_for_other_users(request_user):
            data.pop("user", None)

        # Check user specific reservation restrictions relating to given period.
        resource.validate_reservation_period(reservation, request_user, data=data)

        if data.get("staff_event", False) and not is_staff:
            raise ValidationError(
                dict(staff_event=_("Only allowed to be set by resource managers"))
            )

        if "type" in data:
            if data[
                "type"
            ] != Reservation.TYPE_NORMAL and not resource.can_create_special_type_reservation(  # noqa
                request_user
            ):
                raise ValidationError(
                    {
                        "type": _(
                            "You are not allowed to make a reservation of this type"
                        )
                    }
                )

        if "comments" in data:
            if not resource.can_comment_reservations(request_user):
                raise ValidationError(
                    dict(comments=_("Only allowed to be set by staff members"))
                )

        if "access_code" in data:
            if data["access_code"] is None:
                data["access_code"] = ""

            access_code_enabled = resource.is_access_code_enabled()

            if not access_code_enabled and data["access_code"]:
                raise ValidationError(
                    dict(
                        access_code=_(
                            "This field cannot have a value with this resource"
                        )
                    )
                )

            if (
                access_code_enabled
                and reservation
                and data["access_code"] != reservation.access_code
            ):
                raise ValidationError(
                    dict(access_code=_("This field cannot be changed"))
                )

        # Mark begin of a critical section. Subsequent calls with this same resource
        # will block here until the first request is finished. This is needed so that
        # the validations and possible reservation saving are executed in one block and
        # concurrent requests cannot be validated incorrectly.
        Resource.objects.select_for_update().get(pk=resource.pk)

        # Check maximum number of active reservations per user per resource.
        # Only new reservations are taken into account ie. a normal user can modify
        # an existing reservation even if it exceeds the limit. (one that was created
        # via admin ui for example).
        if reservation is None:
            resource.validate_max_reservations_per_user(request_user)

        # Run model clean
        instance = Reservation(**data)
        try:
            instance.clean(original_reservation=reservation, user=request_user)
        except DjangoValidationError as exc:
            # Convert Django ValidationError to DRF ValidationError so that in the
            # response field specific error messages are added in the field instead of
            # in non_field_messages.
            if not hasattr(exc, "error_dict"):
                raise ValidationError(exc)
            error_dict = {}
            for key, value in exc.error_dict.items():
                error_dict[key] = [error.message for error in value]
            raise ValidationError(error_dict)
        return data

    def to_internal_value(self, data):
        user_data = data.copy().pop("user", None)  # handle user manually
        deserialized_data = super().to_internal_value(data)

        # validate user and convert it to User object
        if user_data:
            UserSerializer(data=user_data).is_valid(raise_exception=True)
            try:
                deserialized_data["user"] = User.objects.get(
                    **{USER_ID_ATTRIBUTE: user_data["id"]}
                )
            except User.DoesNotExist:
                raise ValidationError(
                    {
                        "user": {
                            "id": [
                                _(
                                    'Invalid pk "{pk_value}" - object does not exist.'
                                ).format(pk_value=user_data["id"])
                            ]
                        }
                    }
                )
        return deserialized_data

    def to_representation(self, instance):
        data = super(ReservationSerializer, self).to_representation(instance)
        resource = instance.resource
        request = self.context["request"]
        user = self.context.get("prefetched_user", request.user)

        if request.accepted_renderer.format in ["xlsx", "csv"]:
            data = self.add_report_data(request, instance, data)

        if not resource.can_access_reservation_comments(user):
            del data["comments"]

        if not resource.can_view_reservation_user(user):
            del data["user"]

        if instance.are_extra_fields_visible(user):
            cache = self.context.get("reservation_metadata_set_cache")
            supported_fields = set(
                resource.get_supported_reservation_extra_field_names(cache=cache)
            )
        else:
            supported_fields = set()

        for field_name in RESERVATION_EXTRA_FIELDS:
            if field_name not in supported_fields:
                data.pop(field_name, None)

        if not (
            resource.is_access_code_enabled() and instance.can_view_access_code(user)
        ):
            data.pop("access_code")

        if "access_code" in data and data["access_code"] == "":
            data["access_code"] = None

        if instance.can_view_catering_orders(user):
            data["has_catering_order"] = instance.catering_orders.exists()

        return data

    def add_report_data(self, request, instance, data):
        data = {
            **data,
            "unit": instance.resource.unit.name,  # additional
            "resource": instance.resource.name,  # resource name instead of id
            "begin": instance.begin,  # datetime object
            "end": instance.end,  # datetime object
            "user": instance.user.email if instance.user else "",  # just email
            "created_at": instance.created_at,
            # make sure state is translated
            "state": instance.get_state_display(),
        }

        if request.data.get("includeAccountingFields") == "1":
            order = instance.get_order()
            if order:
                price = order.get_price()
                if price:
                    order_line = order.order_lines.first()
                    user_group = order_line.user_group if order_line else None
                    event_type = order_line.event_type if order_line else None

                    data = {
                        **data,
                        "total_price": price,
                        "cost_center_code": instance.resource.unit.cost_center_code,
                        "sap_cost_center_code": instance.resource.unit.sap_cost_center_code,
                        "sap_sales_organization": instance.resource.unit.sap_sales_organization,
                        "invoice_generated_at": instance.invoice_generated_at,
                        "tax_percentage": order.tax_percentage,
                        "quantity": order.quantity,
                        "unit_price": order.unit_price,
                        "user_group": user_group,
                        "event_type": event_type,
                    }
        return data

    def get_is_own(self, obj):
        return obj.user == self.context["request"].user

    def get_user_permissions(self, obj):
        request = self.context.get("request")
        prefetched_user = self.context.get("prefetched_user", None)
        user = prefetched_user or request.user

        can_modify_and_delete = obj.can_modify(user) if request else False
        return {
            "can_modify": can_modify_and_delete,
            "can_delete": can_modify_and_delete,
        }


class UserFilterBackend(filters.BaseFilterBackend):
    """
    Filter by user uuid and by is_own.
    """

    def filter_queryset(self, request, queryset, view):
        user = request.query_params.get("user", None)
        if user:
            try:
                user_uuid = uuid.UUID(user)
            except ValueError:
                raise exceptions.ParseError(
                    _("Invalid value in filter %(filter)s") % {"filter": "user"}
                )
            queryset = queryset.filter(user__uuid=user_uuid)

        if not request.user.is_authenticated:
            return queryset

        is_own = request.query_params.get("is_own", None)
        if is_own is not None:
            is_own = is_own.lower()
            if is_own in ("true", "t", "yes", "y", "1"):
                queryset = queryset.filter(user=request.user)
            elif is_own in ("false", "f", "no", "n", "0"):
                queryset = queryset.exclude(user=request.user)
            else:
                raise exceptions.ParseError(
                    _("Invalid value in filter %(filter)s") % {"filter": "is_own"}
                )
        return queryset


class ExcludePastFilterBackend(filters.BaseFilterBackend):
    """
    Exclude reservations in the past.
    """

    def filter_queryset(self, request, queryset, view):
        past = request.query_params.get("all", "false")
        past = BooleanField().to_internal_value(past)
        if not past:
            now = timezone.now()
            return queryset.filter(end__gte=now)
        return queryset


class ReservationFilterBackend(filters.BaseFilterBackend):
    """
    Filter reservations by time.
    """

    def filter_queryset(self, request, queryset, view):
        params = request.query_params
        times = {}
        past = False
        for name in ("start", "end"):
            if name not in params:
                continue
            # whenever date filtering is in use, include past reservations
            past = True
            try:
                times[name] = arrow.get(params[name]).to("utc").datetime
            except ParserError:
                raise exceptions.ParseError(
                    "'%s' must be a timestamp in ISO 8601 format" % name
                )
        is_detail_request = "pk" in request.parser_context["kwargs"]
        if not past and not is_detail_request:
            past = params.get("all", "false")
            past = BooleanField().to_internal_value(past)
            if not past:
                now = timezone.now()
                queryset = queryset.filter(end__gte=now)
        if times.get("start", None):
            queryset = queryset.filter(end__gte=times["start"])
        if times.get("end", None):
            queryset = queryset.filter(begin__lte=times["end"])
        return queryset


class NeedManualConfirmationFilterBackend(filters.BaseFilterBackend):
    def filter_queryset(self, request, queryset, view):
        filter_value = request.query_params.get("need_manual_confirmation", None)
        if filter_value is not None:
            need_manual_confirmation = BooleanField().to_internal_value(filter_value)
            return queryset.filter(
                resource__need_manual_confirmation=need_manual_confirmation
            )
        return queryset


class StateFilterBackend(filters.BaseFilterBackend):
    def filter_queryset(self, request, queryset, view):
        state = request.query_params.get("state", None)
        if state:
            queryset = queryset.filter(state__in=state.replace(" ", "").split(","))
        return queryset


class CanApproveFilterBackend(filters.BaseFilterBackend):
    def filter_queryset(self, request, queryset, view):
        filter_value = request.query_params.get("can_approve", None)
        if filter_value:
            queryset = queryset.filter(resource__need_manual_confirmation=True)
            allowed_resources = Resource.objects.with_perm(
                "can_approve_reservation", request.user
            )
            can_approve = BooleanField().to_internal_value(filter_value)
            if can_approve:
                queryset = queryset.filter(resource__in=allowed_resources)
            else:
                queryset = queryset.exclude(resource__in=allowed_resources)
        return queryset


class ReservationFilterSet(django_filters.rest_framework.FilterSet):
    class Meta:
        model = Reservation
        fields = (
            "event_subject",
            "host_name",
            "reserver_name",
            "resource_name",
            "is_favorite_resource",
            "unit",
        )

    @property
    def qs(self):
        qs = super().qs
        user = self.request.user
        query_params = set(self.request.query_params)

        # if any of the extra field related filters are used, restrict results to
        # reservations the user has right to see
        if bool(query_params & set(RESERVATION_EXTRA_FIELDS)):
            qs = qs.extra_fields_visible(user)

        if "has_catering_order" in query_params:
            qs = qs.catering_orders_visible(user)

        return qs

    event_subject = django_filters.CharFilter(lookup_expr="icontains")
    host_name = django_filters.CharFilter(lookup_expr="icontains")
    reserver_name = django_filters.CharFilter(lookup_expr="icontains")
    resource_name = django_filters.CharFilter(
        field_name="resource", lookup_expr="name__icontains"
    )
    is_favorite_resource = django_filters.BooleanFilter(
        method="filter_is_favorite_resource", widget=DRFFilterBooleanWidget
    )
    resource_group = django_filters.Filter(
        field_name="resource__groups__identifier",
        lookup_expr="in",
        widget=django_filters.widgets.CSVWidget,
        distinct=True,
    )
    unit = django_filters.CharFilter(field_name="resource__unit_id")
    has_catering_order = django_filters.BooleanFilter(
        method="filter_has_catering_order", widget=DRFFilterBooleanWidget
    )
    resource = django_filters.Filter(
        lookup_expr="in", widget=django_filters.widgets.CSVWidget
    )

    reserver_info_search = django_filters.CharFilter(
        method="filter_reserver_info_search"
    )

    def filter_is_favorite_resource(self, queryset, name, value):
        user = self.request.user

        if not user.is_authenticated:
            return queryset.none() if value else queryset

        filtering = {"resource__favorited_by": user}
        return queryset.filter(**filtering) if value else queryset.exclude(**filtering)

    def filter_has_catering_order(self, queryset, name, value):
        return queryset.exclude(catering_orders__isnull=value)

    def filter_reserver_info_search(self, queryset, name, value):
        """
        A partial copy of rest_framework.filters.SearchFilter.filter_queryset.
        Needed due to custom filters applied to queryset within this
        ReservationFilterSet.

        Does not support comma separation of values, i.e.
        '?reserver_info_search=foo,bar' will be considered as one string - 'foo,bar'.
        """
        if not value:
            return queryset

        fields = ("user__first_name", "user__last_name", "user__email")
        conditions = []
        for field in fields:
            conditions.append(Q(**{field + "__icontains": value}))

        # assume that first_name and last_name were provided if empty space was found
        if " " in value and value.count(" ") == 1:
            name1, name2 = value.split()
            filters = Q(
                user__first_name__icontains=name1,
                user__last_name__icontains=name2,
            ) | Q(
                user__first_name__icontains=name2,
                user__last_name__icontains=name1,
            )
            conditions.append(filters)

        return queryset.filter(reduce(operator.or_, conditions))


class ReservationPermission(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        return obj.can_modify(request.user, request_method=request.method)


class ReservationAuthenticationLevelPermission(permissions.BasePermission):
    """
    This class matches the authentication level on resource with the current
    authentication backend used to authenticate the user. User authenticated with
    higher level authentication can reserve resource with lower level authentication,
    plus the same level as user's authentication level.

    PIKI login is an exception. Resources whose auth level is PIKI, should only be
    reservable by PIKI library (axiell_aurora) card login. However, PIKI login can
    reserve every resource other than the one that requires strong authentication.

    Users logged in with Tampere City's adfs login should be able to reserve all
    resource.

    User's auth level       Reserveable resource with auth level
      Strong          ->       strong, mid, weak, none
      PIKI            ->       PIKI, mid, weak, none
      Mid             ->       mid, weak, none
      Weak            ->       weak, none
      Tampere City Auth ->     strong, mid, weak, none

    Unit admins/managers and officials who can make reservation should be able to
    bypass this permission.
    """

    message = ""
    STRONG_AUTHENTICATION = ("suomifi",)
    MID_AUTHENTICATION = ("phone",)
    WEAK_AUTHENTICATION = ("google", "github", "facebook", "yletunnus")
    PIKI_AUTHENTICATION = ("axiell_aurora",)
    TAMPERE_CITY_AUTHENTICATION = ("tampere_adfs", "tampereazuread")

    def has_permission(self, request, view):
        resource_id = request.data.get("resource")
        if request.method in permissions.SAFE_METHODS or not resource_id:
            return True

        resource = Resource.objects.get(id=resource_id)
        return self._can_reserve_resource_with_current_login(request, resource)

    def _can_reserve_resource_with_current_login(self, request, resource):
        resource_authentication = resource.authentication
        is_own_reservation = request.data.get("is_own", False)

        if resource_authentication in ("none", ""):
            return True

        # Staffs and users logged in via Tampere ADFS can by pass resource
        # authentication check. Also, reservation owner should be able to edit/delete
        # the reservations reserved by different login methods.
        user_authentication = get_user_auth_backend(request)
        if (
            is_own_reservation
            or request.user.is_staff
            or user_authentication in self.TAMPERE_CITY_AUTHENTICATION
        ):
            return True

        is_PIKI_auth_required = resource_authentication == "PIKI"
        # Resource with PIKI auth level should only be reserved with PIKI login!. Even
        # the strong auth shouldn't be able to reserve such resource.
        if is_PIKI_auth_required:
            if user_authentication in self.PIKI_AUTHENTICATION:
                return True
            else:
                self.message = _(
                    "You need to login with PIKI library card to reserve "
                    "this resource."
                )
                return False

        if user_authentication in self.STRONG_AUTHENTICATION:
            return True

        if user_authentication in [*self.MID_AUTHENTICATION, *self.PIKI_AUTHENTICATION]:
            if resource_authentication in ["mid", "weak"]:
                return True
            else:
                self.message = _(
                    "You need to login with strong authentication to "
                    "reserve this resource."
                )
                return False

        if user_authentication in self.WEAK_AUTHENTICATION:
            if resource_authentication == "weak":
                return True
            elif resource_authentication == "mid":
                self.message = _(
                    "You need to login with mid authentication to reserve "
                    "this resource."
                )
            else:
                self.message = _(
                    "You need to login with strong authentication to "
                    "reserve this resource."
                )

        return False


class BaseReportRenderer(renderers.BaseRenderer):
    def render(self, data, media_type=None, renderer_context=None):
        if not renderer_context or renderer_context["response"].status_code == 404:
            return bytes()

        action = renderer_context["view"].action
        if action not in ("retrieve", "list"):
            return NotAcceptable()

        request = renderer_context["request"]

        kwargs = {
            "exclude_reservation_extra_fields": request.query_params.get(
                "excludeReservationExtraFields"
            )
            == "1",
            "include_accounting_fields": request.query_params.get(
                "includeAccountingFields"
            )
            == "1",
        }

        rows = [data] if action == "retrieve" else data["results"]
        return self.render_report(rows, **kwargs)

    def render_report(
        self, rows, *, exclude_reservation_extra_fields, include_accounting_fields
    ):
        raise NotImplementedError()


class ReservationExcelRenderer(BaseReportRenderer):
    media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    format = "xlsx"
    charset = None
    render_style = "binary"

    def render_report(self, rows, **kwargs):
        return generate_reservation_xlsx(rows, **kwargs)


class ReservationCSVRenderer(BaseReportRenderer):
    media_type = "text/csv"
    format = "csv"
    charset = "utf-8"
    render_style = "binary"

    def render_report(self, rows, **kwargs):
        return generate_reservation_csv(rows, **kwargs)


class ReservationCacheMixin:
    def _preload_permissions(self):
        units = set()
        resource_groups = set()
        resources = set()
        checker = ObjectPermissionChecker(self.request.user)

        for rv in self._page:
            resources.add(rv.resource)
            rv.resource._permission_checker = checker

        for res in resources:
            units.add(res.unit)
            for g in res.groups.all():
                resource_groups.add(g)

        if units:
            checker.prefetch_perms(units)
        if resource_groups:
            checker.prefetch_perms(resource_groups)

    def _get_cache_context(self):
        context = {}
        set_list = ReservationMetadataSet.objects.all().prefetch_related(
            "supported_fields", "required_fields"
        )
        context["reservation_metadata_set_cache"] = {x.id: x for x in set_list}

        self._preload_permissions()
        return context


class ReservationViewSet(
    munigeo_api.GeoModelAPIView, viewsets.ModelViewSet, ReservationCacheMixin
):
    queryset = (
        Reservation.objects.select_related("user", "resource", "resource__unit")
        .prefetch_related("catering_orders", "resource__groups")
        .order_by("begin", "resource__unit__name", "resource__name")
    )
    if settings.RESPA_PAYMENTS_ENABLED:
        queryset = queryset.prefetch_related(
            "order",
            "order__order_lines",
            "order__order_lines__product",
        )
    filter_backends = (
        DjangoFilterBackend,
        filters.OrderingFilter,
        UserFilterBackend,
        ReservationFilterBackend,
        NeedManualConfirmationFilterBackend,
        StateFilterBackend,
        CanApproveFilterBackend,
    )
    filterset_class = ReservationFilterSet
    permission_classes = (
        permissions.IsAuthenticatedOrReadOnly,
        ReservationPermission,
        ReservationAuthenticationLevelPermission,
    )
    renderer_classes = (
        renderers.JSONRenderer,
        ResourcesBrowsableAPIRenderer,
        ReservationExcelRenderer,
        ReservationCSVRenderer,
    )
    pagination_class = ReservationPagination
    authentication_classes = list(drf_settings.DEFAULT_AUTHENTICATION_CLASSES) + [
        TokenAuthentication,
        SessionAuthentication,
    ]
    ordering_fields = ("begin",)

    def get_serializer_class(self):
        if settings.RESPA_PAYMENTS_ENABLED:
            from payments.api.reservation import PaymentsReservationSerializer  # noqa

            return PaymentsReservationSerializer
        else:
            return ReservationSerializer

    def get_serializer(self, *args, **kwargs):
        if "data" not in kwargs and len(args) == 1:
            # It's a read operation
            instance_or_page = args[0]
            if isinstance(instance_or_page, Reservation):
                self._page = [instance_or_page]
            else:
                self._page = instance_or_page

        return super().get_serializer(*args, **kwargs)

    def get_serializer_context(self, *args, **kwargs):
        context = super().get_serializer_context(*args, **kwargs)
        if hasattr(self, "_page"):
            context.update(self._get_cache_context())

        request_user = self.request.user

        if request_user.is_authenticated:
            prefetched_user = (
                get_user_model()
                .objects.prefetch_related(
                    "unit_authorizations", "unit_group_authorizations__subject__members"
                )
                .get(pk=request_user.pk)
            )

            context["prefetched_user"] = prefetched_user

        return context

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user

        # General Administrators can see all reservations
        if is_general_admin(user):
            return queryset

        # normal users can see only their own reservations and reservations that are
        # confirmed, requested or waiting for payment
        filters = Q(
            state__in=(
                Reservation.CONFIRMED,
                Reservation.REQUESTED,
                Reservation.INVOICE_REQUESTED,
                Reservation.WAITING_FOR_PAYMENT,
            )
        )
        if user.is_authenticated:
            filters |= Q(user=user)
        queryset = queryset.filter(filters)

        queryset = queryset.filter(resource__in=Resource.objects.visible_for(user))

        return queryset

    def perform_create(self, serializer):
        override_data = {
            "created_by": self.request.user,
            "modified_by": self.request.user,
        }
        if "user" not in serializer.validated_data:
            override_data["user"] = self.request.user
        override_data["state"] = Reservation.CREATED

        instance = serializer.save(**override_data)

        resource = serializer.validated_data["resource"]

        order = instance.get_order()

        request_invoice = instance.invoice_requested if order else False

        if (
            instance.need_manual_confirmation()
            and not request_invoice
            and not resource.can_bypass_manual_confirmation(self.request.user)
        ):
            new_state = Reservation.REQUESTED
        else:
            if order:
                new_state = (
                    Reservation.INVOICE_REQUESTED
                    if request_invoice
                    else Reservation.WAITING_FOR_PAYMENT
                )
            else:
                new_state = Reservation.CONFIRMED

        instance.set_state(new_state, self.request.user)

    def perform_update(self, serializer):
        old_instance = self.get_object()
        old_state = old_instance.state

        order = old_instance.get_order()

        # invoice requested should only be permitted when creating a new reservation
        serializer.validated_data.pop("invoice_requested", False)

        new_state = serializer.validated_data.pop("state", old_state)
        new_order = serializer.validated_data.pop("order", None)

        new_instance = serializer.save(
            modified_by=self.request.user,
            order=new_order or order,
            invoice_requested=old_instance.invoice_requested,
        )

        if (
            order
            and old_state == Reservation.REQUESTED
            and new_state == Reservation.WAITING_FOR_PAYMENT
        ):
            payment_return_url = serializer.validated_data.pop(
                "payment_return_url", None
            )

            if not payment_return_url:
                raise ValidationError(
                    _("Return URL is required to initiate the payment")
                )
            else:
                # Initiate the payment process
                provider = get_payment_provider(
                    self.request, ui_return_url=payment_return_url
                )
                provider.initiate_payment(order)

        new_instance.set_state(new_state, self.request.user)

    def perform_destroy(self, instance):
        instance.set_state(Reservation.CANCELLED, self.request.user)

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return self._set_content_disposition(request, response)

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        return self._set_content_disposition(request, response, kwargs["pk"])

    def _set_content_disposition(self, request, response, object_id=None):
        format = request.accepted_renderer.format
        if format in ("csv", "xlsx"):
            disposition = (
                f"attachment; filename={_('reservation')}-{object_id}.{format}"
                if object_id
                else f"attachment; filename={_('reservations')}.{format}"
            )
            response["Content-Disposition"] = disposition
        return response


register_view(ReservationViewSet, "reservation")
