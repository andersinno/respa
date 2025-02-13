from django.utils.translation import gettext_lazy as _
from enumfields import Enum


class UnitGroupAuthorizationLevel(Enum):
    admin = 'admin'

    class Labels:
        admin = _("unit group administrator")


class UnitAuthorizationLevel(Enum):
    admin = 'admin'
    manager = 'manager'
    viewer = 'viewer'

    class Labels:
        admin = _("unit administrator")
        manager = _("unit manager")
        viewer = _("unit viewer")


class ReservationInvoiceStatus(Enum):
    TO_BE_MARKED_AS_READY = "to_be_marked_as_ready"
    MARKED_AS_READY = "marked_as_ready"
    CREATED = "created"
    SENT = "sent"
    ERROR = "error"

    class Labels:
        TO_BE_MARKED_AS_READY =  _("To be marked as ready")
        MARKED_AS_READY = _("Marked as ready")
        CREATED = _("Invoice created, waiting to be sent")
        SENT = _("Sent to SAP")
        ERROR = _("Error")
