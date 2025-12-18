from django.utils.translation import gettext_lazy as _
from django.db import models


class UnitGroupAuthorizationLevel(models.TextChoices):
    ADMIN = 'admin', _("unit group administrator")


class UnitAuthorizationLevel(models.TextChoices):
    ADMIN = 'admin', _("unit administrator")
    MANAGER = 'manager', _("unit manager")
    VIEWER = 'viewer', _("unit viewer")


class ReservationInvoiceStatus(models.TextChoices):
    TO_BE_MARKED_AS_READY = "to_be_marked_as_ready", _("To be marked as ready")
    MARKED_AS_READY = "marked_as_ready", _("Marked as ready")
    CREATED = "created", _("Invoice created, waiting to be sent")
    SENT = "sent", _("Sent to SAP")
    ERROR = "error", _("Error")
