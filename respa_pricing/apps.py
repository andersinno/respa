from django.apps import AppConfig
from django.utils.translation import gettext_lazy


class RespaPricingConfig(AppConfig):
    name = "respa_pricing"
    verbose_name = gettext_lazy("Pricing app")
