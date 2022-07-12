from django.conf import settings


def get_current_production_mode(request):
    return {'PRODUCTION_MODE': settings.PRODUCTION_MODE}
