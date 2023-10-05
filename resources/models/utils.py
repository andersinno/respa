import arrow
import base64
import csv
import datetime
import io
import logging
import struct
import time
import xlsxwriter
from django.conf import settings
from django.contrib.sites.models import Site
from django.core.mail import EmailMultiAlternatives
from django.utils import formats, timezone
from django.utils.timezone import localtime
from django.utils.translation import ugettext_lazy as _
from django.utils.translation import ungettext
from icalendar import Calendar, Event, vDatetime, vGeo, vText
from rest_framework.reverse import reverse

DEFAULT_LANG = settings.LANGUAGES[0][0]

RESERVATION_FIELDS = [
    ("unit", "Unit", 30),
    ("resource", "Resource", 30),
    ("begin", "Begin time", 15),
    ("end", "End time", 15),
    ("created_at", "Created at", 15),
    ("user", "User", 30),
    ("comments", "Comments", 30),
    ("staff_event", "Is staff event", 10),
    ("state", "State", 15),
]

RESERVATION_ACCOUNTING_FIELDS = [
    ("user_group", "User group", 15),
    ("event_type", "Event type", 15),
    ("quantity", "Quantity", 15),
    ("unit_price", "Unit price", 15),
    ("total_price", "Total price", 15),
    ("cost_center_code", "CeePos Cost center code", 30),
    ("sap_cost_center_code", "SAP Cost center code", 30),
    ("sap_sales_organization", "SAP Sales Organization code", 30),
    ("invoice_generated_at", "Invoice created", 15),
    ("tax_percentage", "Tax percentage", 15),
]

RESERVATION_DATETIME_FIELDS = [
    "begin",
    "end",
    "created_at",
    "invoice_generated_at",
]


XLSX_HEADER_FORMAT = {"bold": True}
XLSX_DATE_FORMAT = {"num_format": "dd.mm.yyyy hh:mm", "align": "left"}


def get_default_fields(include_accounting_fields):
    fields = RESERVATION_FIELDS[::]
    if include_accounting_fields:
        fields += RESERVATION_ACCOUNTING_FIELDS[::]
    return fields


def get_headers(*, include_extra_fields, include_accounting_fields):
    """Returns list of tuples of (text, width).

    Text values should be translated.

    If `include_extra_fields` is True will also include `RESERVATION_EXTRA_FIELDS`.
    """
    from resources.models import RESERVATION_EXTRA_FIELDS, Reservation

    fields = get_default_fields(include_accounting_fields)

    headers = [(_(header), size) for _field_name, header, size in fields]

    if include_extra_fields:
        headers += [
            (Reservation._meta.get_field(field).verbose_name, 20)
            for field in RESERVATION_EXTRA_FIELDS
        ]

    return headers


def get_row_data(reservation, *, include_extra_fields, include_accounting_fields):
    """Returns list of tuples of (field_name, value).

    If field is missing from reservation data, or empty, inserts empty string.

    Any date values should be converted automatically.

    If `include_extra_fields` is True will also include `RESERVATION_EXTRA_FIELDS`.
    """
    from resources.models import RESERVATION_EXTRA_FIELDS

    row = [
        (name, convert_value(reservation, name))
        for name, _, _ in get_default_fields(include_accounting_fields)
    ]

    if include_extra_fields:
        row += [
            (name, convert_value(reservation, name))
            for name in RESERVATION_EXTRA_FIELDS
        ]

    return row


def convert_value(reservation, name):
    value = reservation.get(name) or ""
    if value and name in RESERVATION_DATETIME_FIELDS:
        return localtime(value).replace(tzinfo=None)
    return value


def save_dt(obj, attr, dt, orig_tz="UTC"):
    """
    Sets given field in an object to a DateTime object with or without
    a time zone converted into UTC time zone from given time zone

    If there is no time zone on the given DateTime, orig_tz will be used
    """
    if dt.tzinfo:
        arr = arrow.get(dt).to("UTC")
    else:
        arr = arrow.get(dt, orig_tz).to("UTC")
    setattr(obj, attr, arr.datetime)


def get_dt(obj, attr, tz):
    return arrow.get(getattr(obj, attr)).to(tz).datetime


def get_translated(obj, attr):
    key = "%s_%s" % (attr, DEFAULT_LANG)
    val = getattr(obj, key, None)
    if not val:
        val = getattr(obj, attr)
    return val


# Needed for slug fields populating
def get_translated_name(obj):
    return get_translated(obj, "name")


def generate_id():
    t = time.time() * 1000000
    b = base64.b32encode(struct.pack(">Q", int(t)).lstrip(b"\x00")).strip(b"=").lower()
    return b.decode("utf8")


def time_to_dtz(time, date=None, arr=None):
    tz = timezone.get_current_timezone()
    if time:
        if date:
            return tz.localize(datetime.datetime.combine(date, time))
        elif arr:
            return tz.localize(
                datetime.datetime(arr.year, arr.month, arr.day, time.hour, time.minute)
            )
    else:
        return None


def is_valid_time_slot(time, time_slot_duration, opening_time):
    """
    Check if given time is correctly aligned with time slots.

    :type time: datetime.datetime
    :type time_slot_duration: datetime.timedelta
    :type opening_time: datetime.datetime
    :rtype: bool
    """
    return not ((time - opening_time) % time_slot_duration)


def humanize_duration(duration):
    """
    Return the given duration in a localized humanized form.

    Examples: "2 hours 30 minutes", "1 hour", "30 minutes"

    :type duration: datetime.timedelta
    :rtype: str
    """
    hours = duration.days * 24 + duration.seconds // 3600
    mins = duration.seconds // 60 % 60
    hours_string = (
        ungettext("%(count)d hour", "%(count)d hours", hours) % {"count": hours}
        if hours
        else None
    )
    mins_string = (
        ungettext("%(count)d minute", "%(count)d minutes", mins) % {"count": mins}
        if mins
        else None
    )
    return " ".join(filter(None, (hours_string, mins_string)))


notification_logger = logging.getLogger("respa.notifications")


def send_respa_mail(email_address, subject, body, html_body=None, attachments=None):
    if not getattr(settings, "RESPA_MAILS_ENABLED", False):
        return

    from_address = (
        getattr(settings, "RESPA_MAILS_FROM_ADDRESS", None)
        or "noreply@%s" % Site.objects.get_current().domain
    )

    notification_logger.info(
        'Sending notification email to %s: "%s"' % (email_address, subject)
    )

    text_content = body
    msg = EmailMultiAlternatives(
        subject, text_content, from_address, [email_address], attachments=attachments
    )
    if html_body:
        msg.attach_alternative(html_body, "text/html")
    msg.send()


def generate_reservation_csv(
    reservations,
    exclude_reservation_extra_fields=False,
    include_accounting_fields=False,
):
    include_extra_fields = not (exclude_reservation_extra_fields)

    output = io.StringIO()
    csv_writer = csv.writer(output)
    csv_writer.writerow(
        [
            header
            for header, _ in get_headers(
                include_extra_fields=include_extra_fields,
                include_accounting_fields=include_accounting_fields,
            )
        ]
    )

    for reservation in reservations:
        csv_writer.writerow(
            [
                value
                for _, value in get_row_data(
                    reservation,
                    include_extra_fields=include_extra_fields,
                    include_accounting_fields=include_accounting_fields,
                )
            ]
        )
    return output.getvalue()


def generate_reservation_xlsx(
    reservations,
    exclude_reservation_extra_fields=False,
    include_accounting_fields=False,
):
    """
    Return reservations in Excel xlsx format

    The parameter is expected to be a list of dicts with fields:
      * unit: unit name str
      * resource: resource name str
      * begin: begin time datetime
      * end: end time datetime
      * staff_event: is staff event bool
      * user: user email str (optional)
      * comments: comments str (optional)
      * all of RESERVATION_EXTRA_FIELDS are optional as well

    :rtype: bytes
    """

    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output)
    worksheet = workbook.add_worksheet()
    include_extra_fields = not (exclude_reservation_extra_fields)

    header_format = workbook.add_format(XLSX_HEADER_FORMAT)

    for column, (header, width) in enumerate(
        get_headers(
            include_extra_fields=include_extra_fields,
            include_accounting_fields=include_accounting_fields,
        )
    ):
        worksheet.write(0, column, str(_(header)), header_format)
        worksheet.set_column(column, column, width)

    date_format = workbook.add_format(XLSX_DATE_FORMAT)

    for row, reservation in enumerate(reservations, 1):
        for column, (name, value) in enumerate(
            get_row_data(
                reservation,
                include_extra_fields=include_extra_fields,
                include_accounting_fields=include_accounting_fields,
            )
        ):
            if name in RESERVATION_DATETIME_FIELDS:
                worksheet.write(row, column, value, date_format)
            else:
                worksheet.write(row, column, value)

    workbook.close()
    return output.getvalue()


def get_object_or_none(cls, **kwargs):
    try:
        return cls.objects.get(**kwargs)
    except cls.DoesNotExist:
        return None


def create_datetime_days_from_now(days_from_now, exclude_extra_day=False):
    """DEPRECATED: use add_days().
    If days_from_now is None, returns None.

    If exclude_extra_day is True, returns current datetime + number of days,
    otherwise returns from start of day + number of days + 1.
    """
    if days_from_now is None:
        return None

    return (
        add_days(days_from_now, from_start_of_day=False)
        if exclude_extra_day
        else add_days(days_from_now + 1, from_start_of_day=True)
    )


def add_days(days_from_now, *, from_start_of_day=True):
    """
    Adds days to current time.

    If from_start_of_day is True, count from start of today.
    """

    now = timezone.now()

    if from_start_of_day:
        now = now.replace(hour=0, minute=0, second=0, microsecond=0)

    return now + datetime.timedelta(days=days_from_now)


def localize_datetime(dt):
    return formats.date_format(timezone.localtime(dt), "DATETIME_FORMAT")


def format_dt_range(language, begin, end):
    if language == "fi":
        # ma 1.1.2017 klo 12.00
        begin_format = r"D j.n.Y \k\l\o G.i"
        if begin.date() == end.date():
            end_format = "G.i"
            sep = "–"
        else:
            end_format = begin_format
            sep = " – "

        res = sep.join(
            [
                formats.date_format(begin, begin_format),
                formats.date_format(end, end_format),
            ]
        )
    else:
        # default to English
        begin_format = r"D j/n/Y G:i"
        if begin.date() == end.date():
            end_format = "G:i"
            sep = "–"
        else:
            end_format = begin_format
            sep = " – "

        res = sep.join(
            [
                formats.date_format(begin, begin_format),
                formats.date_format(end, end_format),
            ]
        )

    return res


def build_reservations_ical_file(reservations):
    """
    Return iCalendar file containing given reservations
    """

    cal = Calendar()
    for reservation in reservations:
        event = Event()
        begin_utc = timezone.localtime(reservation.begin, timezone.utc)
        end_utc = timezone.localtime(reservation.end, timezone.utc)
        event["uid"] = "respa_reservation_{}".format(reservation.id)
        event["dtstart"] = vDatetime(begin_utc)
        event["dtend"] = vDatetime(end_utc)
        unit = reservation.resource.unit
        event["location"] = vText(
            "{} {} {}".format(unit.name, unit.street_address, unit.address_zip)
        )
        if unit.location:
            event["geo"] = vGeo(unit.location)
        event["summary"] = vText("{} {}".format(unit.name, reservation.resource.name))
        cal.add_component(event)
    return cal.to_ical()


def build_ical_feed_url(ical_token, request):
    """
    Return iCal feed url for given token without query parameters
    """

    url = reverse("ical-feed", kwargs={"ical_token": ical_token}, request=request)
    return url[: url.find("?")]
