import django.dispatch

reservation_confirmed = django.dispatch.Signal()
reservation_modified = django.dispatch.Signal()
reservation_cancelled = django.dispatch.Signal()
