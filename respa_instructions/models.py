from django.db import models
from django.utils.translation import ugettext_lazy as _

from ckeditor_uploader.fields import RichTextUploadingField


class RespaInstruction(models.Model):
    ADMIN = 'admin'
    APPLICANT = 'applicant'
    APPLICABLE_FOR_CHOICES = (
        (ADMIN, _('Admin')),
        (APPLICANT, _('Applicant')),
    )

    order = models.PositiveIntegerField()
    title = models.CharField(
        verbose_name=_('Title'),
        max_length=264,
    )
    applicable_for = models.CharField(
        verbose_name=_('Applicable for'),
        max_length=32,
        choices=APPLICABLE_FOR_CHOICES,
        default=APPLICANT,
    )
    content = RichTextUploadingField()
    active = models.BooleanField(verbose_name=_('Active'), default=False)

    class Meta:
        ordering = ('order',)

    def __str__(self):
        return self.title
