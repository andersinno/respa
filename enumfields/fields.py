from django.db import models

class EnumField(models.CharField):
    """
    Minimal stub to satisfy old migrations that reference enumfields.fields.EnumField.
    This does NOT implement any enumfields behavior — it only keeps migrations working.
    """
    def __init__(self, enum=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
