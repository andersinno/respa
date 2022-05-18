import datetime, io, re, xlsxwriter
from collections import namedtuple

from django.db.models import Q
from django.utils import timezone
from django.utils.translation import ugettext_lazy as _
from rest_framework import renderers, generics, serializers
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response

from .base import BaseReport
from resources.models import Reservation, Resource, Unit, Period
from resources.models.availability import get_opening_hours


class Range(namedtuple('Range', ['start', 'end'])):
    """
    Object containing a time range.
    Created for readibility.

    start   datetime.timedelta
    end     datetime.timedelta
    """
    pass


def get_time_overlap(r1, r2):
    """
    Returns overlap of time between 2 time ranges.

    Example:
    User selected range: 09:00 - 15:00.
    Reservation length: 08:00 - 11:00.
    Overlap would be 2 hours. So between
    09:00 - 11:00.

    :param r1: Range
    :param r2: Range
    :rtype: datetime.timedelta
    """

    latest_start = max(r1.start, r2.start)
    earliest_end = min(r1.end, r2.end)
    delta = earliest_end - latest_start

    overlap = max(0, delta.total_seconds())

    if overlap == 0:
        return datetime.timedelta(hours=0, minutes=0)

    return delta


class ReservationRateReportExcelRenderer(renderers.BaseRenderer):
    media_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    format = 'xlsx'
    charset = None
    render_style = 'binary'

    def _hour_min_string(self, time1, time2=None):
        """
        Converts decimal time(s) into readable string:
        'Xh XXmin' or 'Xh XXmin / Xh XXmin'

        :param time1: float
        :param time2: float
        :rtype: string
        """

        hours1 = int(time1)
        mins1 = int(round((time1 * 60) % 60))

        if time2 is None:
            return f"{hours1}h {mins1}min"

        hours2 = int(time2)
        mins2 = int(round((time2 * 60) % 60))

        return f"{hours1}h {mins1}min / {hours2}h {mins2}min"

    def _data_to_representation(self, data):
        """
        Compiles data to be presentation ready for renderer.
        """

        begin = data.pop("begin")
        end = data.pop("end")
    
        day_period = f"{begin.strftime('%d.%m.%Y')} - {end.strftime('%d.%m.%Y')}"
        time_period = f"{begin.strftime('%H.%M')} - {end.strftime('%H.%M')}"

        data["day_period"] = day_period
        data["time_period"] = time_period

        for unit in data["units"]:
            unit_reserved_time = datetime.timedelta()
            unit_max_reservable_time = datetime.timedelta()

            for resource in unit["resources"]:
                unit_max_reservable_time += resource["max_reservable_time"]

                resource_reserved_time = datetime.timedelta()

                for r in resource["reservations"]:
                    resource_reserved_time += r.pop("reserved_time")
    
                unit_reserved_time += resource_reserved_time

                resource["reserved_time_sum"] = self._hour_min_string(resource_reserved_time.total_seconds() / 3600)

            unit_reservation_rate = self._hour_min_string(
                unit_reserved_time.total_seconds() / 3600,
                time2=unit_max_reservable_time.total_seconds() / 3600,
            )

            unit["unit_reservation_rate"] = unit_reservation_rate

        return data

    def render(self, data, media_type=None, renderer_context=None):
        """
        Renders a separate sheet for each unit. Each sheet will contain
        a summary of unit info, reservation rates and sums of reserved
        time per resource. Below the summary will be listings of
        reservation details per resource.

        Data will mostly be in string types because it is compiled
        to a ready-to-present format for easier rendering. See
        function: _data_to_representation.

        Returns an Excel file in xlsx format.

        :rtype: bytes
        """

        data = self._data_to_representation({
            "units": data,
            **renderer_context
        })

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output)
        header_format = workbook.add_format({'bold': True})

        summary_headers = [
            (0, 0, "Kiinteistö"),
            (0, 1, "Katuosoite"),
            (0, 2, "Ajankohta"),
            (0, 3, "Aikaväli"),
            (0, 4, "Kiinteistön varausaste"),
            (3, 0, "Resurssin nimi"),
            (3, 1, "Tilatyyppi"),
            (3, 2, "Varatut ajat yhteensä"),
        ]

        reservation_headers = [
            (0, "Varaajan nimi"),
            (1, "Varauksen nimi"),
            (2, "Alkoi"),
            (3, "Päättyi"),
        ]

        sheet_name_pattern = re.compile("[\\[\\]:*?/\\\\]")

        for count, unit in enumerate(data["units"]):
            row_pos = 0
            
            # Do some string processing to avoid excel errors.
            # 1. Remove unallowed characters
            # 2. Append #[count] to end of string to have a unique sheet name
            # 3. Limit sheet name to the last 31 characters
            sheet_name = re.sub(sheet_name_pattern, "", unit["name"])
            sheet_name = f"{sheet_name} #{count}"[-31:]

            sheet = workbook.add_worksheet(sheet_name)
            
            sheet.set_column(0, 5, 40) # Sets width of columns

            for header in summary_headers:
                sheet.write(*header, header_format)

            sheet.write(1, 0, unit["name"])
            sheet.write(1, 1, unit["street_address"])
            sheet.write(1, 2, data["day_period"])
            sheet.write(1, 3, data["time_period"])
            sheet.write(1, 4, unit["unit_reservation_rate"])

            row_pos += 4

            for resource in unit["resources"]:
                sheet.write(row_pos, 0, resource["name"])
                sheet.write(row_pos, 1, resource["type"])
                sheet.write(row_pos, 2, resource["reserved_time_sum"])
                row_pos += 1

            row_pos += 2
            
            for resource in unit["resources"]:
                sheet.write(row_pos, 0, resource["name"], header_format)
                sheet.write(row_pos, 1, resource["type"], header_format)

                row_pos += 1
        
                for header in reservation_headers:
                    col, text = header
                    sheet.write(row_pos, col, text, header_format)

                row_pos += 1

                for reservation in resource["reservations"]:
                    sheet.write(row_pos, 0, reservation["reserver_name"])
                    sheet.write(row_pos, 1, reservation["event_subject"])
                    sheet.write(row_pos, 2, reservation["begin"])
                    sheet.write(row_pos, 3, reservation["end"])
                    row_pos += 1
                
                row_pos += 4

        workbook.close()

        return output.getvalue()


class ReservationSerializer(serializers.ModelSerializer):
    reserved_time = serializers.SerializerMethodField()
    begin = serializers.SerializerMethodField()
    end = serializers.SerializerMethodField()

    class Meta:
        model = Reservation
        fields = (
            "begin",
            "end",
            "reserver_name",
            "event_subject",
            "reserved_time",
        )

    def get_reserved_time(self, obj):
        begin = self.context["begin"]
        end = self.context["end"]

        res_begin = timezone.localtime(obj.begin)
        res_end = timezone.localtime(obj.end)

        td1 = datetime.timedelta(hours=res_begin.hour, minutes=res_begin.minute)
        td2 = datetime.timedelta(hours=res_end.hour, minutes=res_end.minute)
        r1 = Range(start=td1, end=td2)

        td1 = datetime.timedelta(hours=begin.hour, minutes=begin.minute)
        td2 = datetime.timedelta(hours=end.hour, minutes=end.minute)
        r2 = Range(start=td1, end=td2)

        return get_time_overlap(r1, r2)

    def get_begin(self, obj):
        return timezone.localtime(obj.begin).strftime("%d.%m.%Y %H.%M")

    def get_end(self, obj):
        return timezone.localtime(obj.end).strftime("%d.%m.%Y %H.%M")


class ResourceSerializer(serializers.ModelSerializer):
    reservations = serializers.SerializerMethodField()
    max_reservable_time = serializers.SerializerMethodField()
    type = serializers.CharField(source="type.name")

    class Meta:
        model = Resource
        fields = (
            "type",
            "name",
            "reservations",
            "max_reservable_time",
        )

    def get_max_reservable_time(self, obj):
        begin = self.context["begin"]
        end = self.context["end"]

        unit_periods = Period.objects.filter(unit=obj.unit)
        resource_periods = Period.objects.filter(resource=obj)

        # Prioritize resource periods over unit periods.
        for period in unit_periods:
            period.priority = 0
        for period in resource_periods:
            period.priority = 1

        opening_hours = get_opening_hours(
            "Europe/Helsinki",
            list(unit_periods) + list(resource_periods),
            begin,
            end=end
        )
        
        delta_sum = datetime.timedelta()

        for date in opening_hours:
            opens = opening_hours[date][0]["opens"]
            closes = opening_hours[date][0]["closes"]
            if opens is not None and closes is not None:
                td1 = datetime.timedelta(hours=begin.hour, minutes=begin.minute)
                td2 = datetime.timedelta(hours=end.hour, minutes=end.minute)
                r1 = Range(start=td1, end=td2)

                td1 = datetime.timedelta(hours=opens.hour, minutes=opens.minute)
                td2 = datetime.timedelta(hours=closes.hour, minutes=closes.minute)
                r2 = Range(start=td1, end=td2)
                delta_sum += get_time_overlap(r1, r2)

        return delta_sum

    def get_reservations(self, obj):
        begin = self.context["begin"]
        end = self.context["end"]

        qs = (
            Reservation.objects
            .filter(resource=obj)
            .exclude(Q(
                Q(begin__date__gt=end.date()) |
                Q(end__date__lt=begin.date()) |
                Q(begin__time__gt=end.time()) |
                Q(end__time__lt=begin.time())
            ))
        ).order_by("-begin")

        serializer = ReservationSerializer(qs, many=True, context=self.context)

        return serializer.data


class UnitSerializer(serializers.ModelSerializer):
    resources = serializers.SerializerMethodField()

    class Meta:
        model = Unit
        fields = (
            "name",
            "street_address",
            "resources"
        )

    def get_resources(self, obj):
        qs = Resource.objects.filter(unit=obj).order_by("type")

        serializer = ResourceSerializer(qs, many=True, context=self.context)

        return serializer.data


class ReservationRateReport(BaseReport):
    serializer_class = UnitSerializer
    renderer_classes = (ReservationRateReportExcelRenderer,)

    def get_queryset(self):
        return Unit.objects.all()

    def filter_queryset(self, queryset):
        params = self.request.query_params

        units = params.getlist("units")
        start_date = params.get("start_date")
        end_date = params.get("end_date")
        start_time = params.get("start_time", "08:00")
        end_time = params.get("end_time", "16:00")

        if not units:
            raise ValidationError(_("Missing unit id(s)"))

        if not start_date or not end_date:
            raise ValidationError(_("Missing start date or end date"))

        try:
            begin = datetime.datetime.strptime(
                f"{start_date} {start_time}", "%Y-%m-%d %H:%M"
            )
            end = datetime.datetime.strptime(
                f"{end_date} {end_time}", "%Y-%m-%d %H:%M"
            )
        except ValueError as e:
            raise ValidationError(_("Dates be in Y-m-d format and times must be in H:M format"))

        if begin > end or begin.time() > end.time():
            raise ValidationError(_("End time must be after begin time"))

        self._begin = timezone.localtime(timezone.make_aware(begin))
        self._end = timezone.localtime(timezone.make_aware(end))

        return queryset.filter(id__in=units)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['begin'] = self._begin
        context['end'] = self._end
        return context

    def get_renderer_context(self):
        context = super().get_renderer_context()
        if hasattr(self, "_begin") and hasattr(self, "_end"):
            context['begin'] = self._begin
            context['end'] = self._end
        return context

    def get_filename(self, request, validated_data):
        return 'varausasteraportti.xlsx'
