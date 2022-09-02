from modeltranslation.translator import TranslationOptions, register

from .models import RespaInstruction


@register(RespaInstruction)
class RespaInstructionTranslationOptions(TranslationOptions):
    fields = ('content',)
