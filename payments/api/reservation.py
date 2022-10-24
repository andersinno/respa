from decimal import Decimal
from django.utils.translation import ugettext_lazy as _
from rest_framework import exceptions, serializers, status
from rest_framework.exceptions import PermissionDenied
from django.utils.duration import duration_string

from payments.exceptions import (
    DuplicateOrderError,
    PayloadValidationError,
    PaymentCreationFailedError,
    RespaPaymentError,
    ServiceUnavailableError,
    UnknownReturnCodeError,
)
from resources.api.reservation import ReservationSerializer
from respa_pricing.models import UserGroupPriceListItem, EventPriceListItem, PriceList
from ..models import OrderLine, Product
from ..providers import get_payment_provider
from .base import OrderSerializerBase, ProductSerializer


class ReservationEndpointOrderSerializer(OrderSerializerBase):
    id = serializers.ReadOnlyField(source='order_number')
    return_url = serializers.CharField(write_only=True)
    payment_url = serializers.SerializerMethodField()

    class Meta(OrderSerializerBase.Meta):
        fields = OrderSerializerBase.Meta.fields + ('id', 'return_url', 'payment_url')

    def create(self, validated_data):
        order_lines_data = validated_data.pop('order_lines', [])
        return_url = validated_data.pop('return_url', '')
        order = super().create(validated_data)

        for order_line_data in order_lines_data:
            order_line_price_info = PriceList.get_price_info(
                order_line_data['product'],
                order_line_data.pop('user_group'),
                order_line_data.pop('event_type', ''),
                validated_data['reservation'].begin,
                validated_data['reservation'].end,

            )
            order_line_data['unit_price'] = Decimal(order_line_price_info['amount'])
            order_line_data['total_price'] = Decimal(order_line_price_info['total_price'])
            price_source = order_line_price_info['price_source']
            # order_line_data['price_source'] = price_source
            order_line_data['tax_percentage'] = price_source.tax_percentage
            order_line_data['price_period'] = price_source.price_period
            order_line_data['price_type'] = price_source.price_type
            OrderLine.objects.create(order=order, **order_line_data)

        payments = get_payment_provider(request=self.context['request'],
                                        ui_return_url=return_url)
        try:
            self.context['payment_url'] = payments.initiate_payment(order)
        except DuplicateOrderError as doe:
            raise exceptions.APIException(detail=str(doe),
                                          code=status.HTTP_409_CONFLICT)
        except (PayloadValidationError, PaymentCreationFailedError, UnknownReturnCodeError) as e:
            raise exceptions.APIException(detail=str(e),
                                          code=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except ServiceUnavailableError as sue:
            raise exceptions.APIException(detail=str(sue),
                                          code=status.HTTP_503_SERVICE_UNAVAILABLE)
        except RespaPaymentError as pe:
            raise exceptions.APIException(detail=str(pe),
                                          code=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return order

    def get_payment_url(self, obj):
        return self.context.get('payment_url', '')

    def validate_order_lines(self, order_lines):
        # Check order contains order lines
        if not order_lines:
            raise serializers.ValidationError(_('At least one order line required.'))

        # Check products in order lines are unique
        product_ids = [ol['product'].product_id for ol in order_lines]
        if len(product_ids) > len(set(product_ids)):
            raise serializers.ValidationError(_('Order lines cannot contain duplicate products.'))

        resource = self.context.get('resource')
        if resource and resource.has_rent():
            if not any(ol['product'].type == Product.RENT for ol in order_lines):
                raise serializers.ValidationError(_('The order must contain at least one product of type "rent".'))

        return order_lines

    def to_internal_value(self, data):
        resource = self.context.get('resource')
        available_products = resource.products.current() if resource else []
        self.context.update({'available_products': available_products})
        return super().to_internal_value(data)

    def to_representation(self, instance):
        data = super().to_representation(instance)

        if self.context['view'].action != 'create':
            data.pop('payment_url', None)

        return data


class PaymentsReservationSerializer(ReservationSerializer):
    order = serializers.SlugRelatedField('order_number', read_only=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.context['view'].action == 'create':
            request = self.context.get('request')
            resource = self.context.get('resource')

            if resource and resource.free_to_use:
                order_required = False
            elif resource and request:
                order_required = resource.has_rent() and not resource.can_bypass_payment(request.user)
            elif resource:
                order_required = resource.has_rent()
            else:
                order_required = True

            self.fields['order'] = ReservationEndpointOrderSerializer(required=order_required)
        elif 'order_detail' in self.context['includes']:
            self.fields['order'] = ReservationEndpointOrderSerializer(read_only=True)

    class Meta(ReservationSerializer.Meta):
        fields = ReservationSerializer.Meta.fields + ['order']

    def to_representation(self, instance):
        data = super().to_representation(instance)
        prefetched_user = self.context.get('prefetched_user', None)
        user = prefetched_user or self.context['request'].user

        if not instance.can_view_product_orders(user):
            data.pop('order', None)
        else:
            if hasattr(instance, 'order'):
                order_lines = instance.order.order_lines.all()
                # TODO: What should happen if price_source's field value changes
                # And there are multiple order lines ???
                order_line = order_lines.first()
                data['price_info'] = {}
                data['price_info']['amount'] = str(order_line.unit_price)
                data['price_info']['period'] = duration_string(order_line.price_period)
                data['price_info']['tax_percentage'] = str(order_line.tax_percentage)
                data['price_info']['total_price'] = str(order_line.total_price)
                data['price_info']['type'] = order_line.price_type
        return data

    def create(self, validated_data):
        order_data = validated_data.pop('order', None)
        reservation = super().create(validated_data)

        if order_data:
            if not reservation.can_add_product_order(self.context['request'].user):
                raise PermissionDenied()

            order_data['reservation'] = reservation
            ReservationEndpointOrderSerializer(context=self.context).create(validated_data=order_data)

        return reservation

    def validate(self, data):
        order_data = data.pop('order', None)
        data = super().validate(data)
        data['order'] = order_data
        return data
