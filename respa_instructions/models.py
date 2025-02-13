from ckeditor_uploader.fields import RichTextUploadingField
from django.db import models
from django.utils.translation import gettext_lazy as _


class RespaInstruction(models.Model):
    ADMIN = "admin"
    USER = "user"
    APPLICABLE_FOR_CHOICES = (
        (ADMIN, _("Admin")),
        (USER, _("User")),
    )

    order = models.PositiveIntegerField(verbose_name=_("Ordering"))
    title = models.CharField(
        verbose_name=_("Title"),
        max_length=264,
    )
    applicable_for = models.CharField(
        verbose_name=_("Applicable for"),
        max_length=32,
        choices=APPLICABLE_FOR_CHOICES,
        default=USER,
    )
    content = RichTextUploadingField(verbose_name=_("Content"))
    active = models.BooleanField(verbose_name=_("Active"), default=False)

    class Meta:
        verbose_name = _("Instruction")
        verbose_name_plural = _("Instructions")
        ordering = ("order",)

    def __str__(self):
        return self.title
