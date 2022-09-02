from ckeditor_uploader.widgets import CKEditorUploadingWidget
from django import forms
from django.contrib.admin import site as admin_site
from modeltranslation.admin import TranslationAdmin

from .models import RespaInstruction


class RespaInstructionAdminForm(forms.ModelForm):
    content = forms.CharField(widget=CKEditorUploadingWidget, required=False)

    class Meta:
        model = RespaInstruction
        fields = ("active", "order", "title", "applicable_for", "content")


class RespaInstructionAdmin(TranslationAdmin):
    form = RespaInstructionAdminForm
    list_display = ("order", "title", "active")


admin_site.register(RespaInstruction, RespaInstructionAdmin)
