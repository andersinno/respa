from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from resources.api.base import register_view
from resources.models import Reservation

from ..api.base import OrderLineSerializer, OrderSerializerBase
from ..models import Order, OrderLine


class PriceEndpointOrderSerializer(OrderSerializerBase):
    # these fields are actually returned from the API as well, but because
    # they are non-model fields, it seems to be easier to mark them as write
    # only and add them manually to returned data in the viewset
    begin = serializers.DateTimeField(write_only=True)
    end = serializers.DateTimeField(write_only=True)

    class Meta(OrderSerializerBase.Meta):
        fields = ('order_lines', 'price', 'begin', 'end')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # None means "all", we don't want product availability validation
        self.context['available_products'] = None
