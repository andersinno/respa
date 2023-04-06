from django.utils.duration import duration_string
from django.utils.translation import ugettext_lazy as _
from rest_framework import serializers

from resources.api.base import TranslatedModelSerializer

from ..models import Order, OrderLine, Product


class ProductSerializer(TranslatedModelSerializer):
    id = serializers.CharField(source='product_id')

    class Meta:
        model = Product
        fields = (
            'id', 'type', 'name', 'description'
        )


class OrderLineSerializer(serializers.ModelSerializer):
    product = serializers.SlugRelatedField(queryset=Product.objects.current(), slug_field='product_id')
    price = serializers.CharField(source='get_price', read_only=True)
    unit_price = serializers.CharField(read_only=True)
    user_group = serializers.CharField(write_only=True)
    event_type = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = OrderLine
        fields = ('product', 'quantity', 'unit_price', 'price', 'user_group', 'event_type')

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['product'] = ProductSerializer(instance.product).data
        return data

    def validate_product(self, product):
        available_products = self.context['available_products']
        # available_products None means "all".
        # The price check endpoint uses that because available products don't
        # make sense in it's context (because there is no resource),
        if available_products is not None:
            if product not in available_products:
                raise serializers.ValidationError(_("This product isn't available on the resource."))
        return product


class OrderSerializerBase(serializers.ModelSerializer):
    order_lines = OrderLineSerializer(many=True)
    price = serializers.CharField(source='get_price', read_only=True)

    class Meta:
        model = Order
        fields = ('state', 'order_lines', 'price')
