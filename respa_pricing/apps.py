from django.apps import AppConfig
from django.utils.translation import ugettext_lazy


class RespaPricingConfig(AppConfig):
    name = "respa_pricing"
    verbose_name = ugettext_lazy("Pricing app")
