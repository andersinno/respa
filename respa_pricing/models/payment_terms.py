from django.db import models
from django.utils.translation import ugettext_lazy as _

from resources.models.utils import get_translated_name


class RespaPaymentTerm(models.Model):
    name = models.CharField(verbose_name=_('Name'), max_length=200)
    text = models.TextField(verbose_name=_('Description'), blank=True)
    payment_is_refundable = models.BooleanField(
        verbose_name=_('Payment is refundable'),
        default=False,
    )
    refund_percentage = models.DecimalField(
        verbose_name=_('Deductible percentage if reservation is refunded'),
        blank=True,
        null=True,
        max_digits=5,
        decimal_places=2,
    )
    cancellation_min_days_in_advance = models.PositiveIntegerField(
        verbose_name=_('The customer can cancel the reservation (days) before the reservation starts.'),
        default=0,
        blank=True,
    )

    def __str__(self):
        return get_translated_name(self)
