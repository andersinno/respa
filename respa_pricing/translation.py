from modeltranslation.translator import TranslationOptions, register

from .models import UserGroup, EventType


@register(UserGroup)
class UserGroupTranslationOptions(TranslationOptions):
    fields = ["name"]


@register(EventType)
class EventTypeTranslationOptions(TranslationOptions):
    fields = ["name"]
