from datetime import datetime, timedelta
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import OuterRef, Q, Subquery
from django.utils import translation
from django.utils.formats import localize
from django.utils.functional import cached_property
from django.utils import timezone
from django.utils.translation import ugettext_lazy as _
from rest_framework import serializers

from resources.models import Reservation, Resource
from resources.models.utils import generate_id

from .exceptions import (
    OrderStateTransitionError,
    PaymentAlreadyCompletedError,
    PaymentCancellationFailedError,
)
from .utils import convert_aftertax_to_pretax, get_price_period_display, rounded

# The best way for representing non existing archived_at would be using None for it,
# but that would not work with the unique_together constraint, which brings many
# benefits, so we use this sentinel value instead of None.
ARCHIVED_AT_NONE = datetime(9999, 12, 31, tzinfo=timezone.utc)

TAX_PERCENTAGES = [
    Decimal(x)
    for x in (
        "0.00",
        "10.00",
        "14.00",
        "24.00",
    )
]

DEFAULT_TAX_PERCENTAGE = Decimal("24.00")
PRICE_PER_PERIOD = "per_period"
PRICE_FIXED = "fixed"
PRICE_TYPE_CHOICES = (
    (PRICE_PER_PERIOD, _("per period")),
    (PRICE_FIXED, _("fixed")),
)


class ProductQuerySet(models.QuerySet):
    def current(self):
        return self.filter(archived_at=ARCHIVED_AT_NONE)

    def rents(self):
        return self.filter(type=Product.RENT)


class Product(models.Model):
    RENT = "rent"
    EXTRA = "extra"
    TYPE_CHOICES = (
        (RENT, _("rent")),
        (EXTRA, _("extra")),
    )

    created_at = models.DateTimeField(verbose_name=_("created at"), auto_now_add=True)

    # This ID is common to all versions of the same product, and is the one
    # used as ID in the API.
    product_id = models.CharField(
        max_length=100,
        verbose_name=_("internal product ID"),
        editable=False,
        db_index=True,
    )

    # archived_at determines when this version of the product has been either (soft)
    # deleted or replaced by a newer version. Value ARCHIVED_AT_NONE means this is the
    # current version in use.
    archived_at = models.DateTimeField(
        verbose_name=_("archived_at"),
        db_index=True,
        editable=False,
        default=ARCHIVED_AT_NONE,
    )

    type = models.CharField(
        max_length=32, verbose_name=_("type"), choices=TYPE_CHOICES, default=RENT
    )
    sku = models.CharField(max_length=255, verbose_name=_("SKU"), blank=True)
    name = models.CharField(max_length=100, verbose_name=_("name"), blank=True)
    description = models.TextField(verbose_name=_("description"), blank=True)
    resources = models.ManyToManyField(
        Resource, verbose_name=_("resources"), related_name="products", blank=True
    )

    objects = ProductQuerySet.as_manager()

    class Meta:
        verbose_name = _("product")
        verbose_name_plural = _("products")
        ordering = ("product_id",)
        unique_together = ("archived_at", "product_id")

    def __str__(self):
        return "{} ({})".format(self.name, self.product_id)

    def save(self, *args, **kwargs):
        if self.id:
            resources = self.resources.all()
            Product.objects.filter(id=self.id).update(archived_at=timezone.now())
            self.id = None
        else:
            resources = []
            self.product_id = generate_id()

        super().save(*args, **kwargs)

        if resources:
            self.resources.set(resources)

    def delete(self, *args, **kwargs):
        Product.objects.filter(id=self.id).update(archived_at=timezone.now())


class OrderQuerySet(models.QuerySet):
    def can_view(self, user):
        if not user.is_authenticated:
            return self.none()

        allowed_resources = Resource.objects.with_perm(
            "can_view_reservation_product_orders", user
        )
        allowed_reservations = Reservation.objects.filter(
            Q(resource__in=allowed_resources) | Q(user=user)
        )

        return self.filter(reservation__in=allowed_reservations)

    def update_expired(self) -> int:
        """
        All WAITING Orders should be automatically expired if:

        1. Reservation status is REQUESTED
           AND approval was requested over 3 days ago (Reservation.requested_at) OR

        2. Reservation status is WAITING_FOR_PAYMENT
           AND the reservation was approved more than 24 hours ago
           (Reservation.approved_at) OR

        3. Reservation status is WAITING_FOR_PAYMENT
           AND reservation didn’t need manual approval (Reservation.approved_at==null)
           AND order is older than settings.RESPA_PAYMENTS_PAYMENT_WAITING_TIME

        If the Order has actually already been paid but for some reason the state
        doesn't reflect that (should not happen), confirm the order instead.

        Returns:
            tuple of number of orders expired and number of orders confirmed
        """

        now = timezone.now()

        for_expiry = (
            self.annotate(
                created_at=Subquery(
                    OrderLogEntry.objects.filter(order=OuterRef("pk"))
                    .order_by("id")
                    .values("timestamp")[:1]
                )
            )
            .filter(
                Q(
                    reservation__requested_at__lt=now - timedelta(days=3),
                    reservation__state=Reservation.REQUESTED,
                )
                | Q(
                    Q(reservation__approved_at__lt=now - timedelta(hours=24))
                    | Q(
                        reservation__approved_at__isnull=True,
                        created_at__lt=now
                        - timedelta(
                            minutes=settings.RESPA_PAYMENTS_PAYMENT_WAITING_TIME
                        ),
                    ),
                    reservation__state=Reservation.WAITING_FOR_PAYMENT,
                ),
                state=self.model.WAITING,
            )
            .distinct()
        )

        num_of_orders_expired = 0
        num_of_order_confirmed = 0

        for order in for_expiry:
            try:
                order.set_state(self.model.EXPIRED)
                num_of_orders_expired += 1
            except PaymentAlreadyCompletedError:
                order.set_state(self.model.CONFIRMED)
                num_of_order_confirmed += 1

        return (num_of_orders_expired, num_of_order_confirmed)


class Order(models.Model):
    WAITING = "waiting"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CANCELLED = "cancelled"

    STATE_CHOICES = (
        (WAITING, _("waiting")),
        (CONFIRMED, _("confirmed")),
        (REJECTED, _("rejected")),
        (EXPIRED, _("expired")),
        (CANCELLED, _("cancelled")),
    )

    payment_link = models.URLField(verbose_name=_("Payment Link"), blank=True)

    state = models.CharField(
        max_length=32, verbose_name=_("state"), choices=STATE_CHOICES, default=WAITING
    )
    order_number = models.CharField(
        max_length=64, verbose_name=_("order number"), unique=True, default=generate_id
    )

    reservation = models.OneToOneField(
        Reservation,
        verbose_name=_("reservation"),
        related_name="order",
        on_delete=models.PROTECT,
    )

    objects = OrderQuerySet.as_manager()

    class Meta:
        verbose_name = _("order")
        verbose_name_plural = _("orders")
        ordering = ("id",)

    def __str__(self):
        return "({}) {}".format(self.order_number, self.reservation)

    @cached_property
    def created_at(self):
        first_log_entry = self.log_entries.first()
        return first_log_entry.timestamp if first_log_entry else None

    def save(self, *args, **kwargs):
        is_new = not bool(self.id)
        super().save(*args, **kwargs)

        if is_new:
            self.create_log_entry(state_change=self.state, message="Created.")

    def get_order_lines(self):
        # This allows us to do price calculations using order line objects that
        # don't exist in the db. That is needed in the price check endpoint.
        return (
            self._in_memory_order_lines
            if hasattr(self, "_in_memory_order_lines")
            else self.order_lines.all()
        )

    def get_price(self) -> Decimal:
        return sum(order_line.get_price() for order_line in self.get_order_lines())

    def set_state(
        self, new_state: str, log_message: str = None, save: bool = True
    ) -> None:
        assert new_state in (
            Order.WAITING,
            Order.CONFIRMED,
            Order.REJECTED,
            Order.EXPIRED,
            Order.CANCELLED,
        )

        old_state = self.state
        if new_state == old_state:
            return

        valid_state_changes = {
            Order.WAITING: (Order.CONFIRMED, Order.REJECTED, Order.EXPIRED),
            Order.CONFIRMED: (Order.CANCELLED,),
        }
        valid_new_states = valid_state_changes.get(old_state, ())

        if new_state not in valid_new_states:
            raise OrderStateTransitionError(
                'Cannot set order {} state to "{}", it is in an invalid state "{}".'.format(  # noqa
                    self.order_number, new_state, old_state
                )
            )

        if new_state in (Order.EXPIRED, Order.CANCELLED):
            if self.reservation.state == Reservation.WAITING_FOR_PAYMENT:
                # Cancel any open payments to make sure the order cannot
                # be paid after it's been cancelled in Respa.

                from .providers import get_payment_provider

                payment_provider = get_payment_provider(request=None)
                try:
                    payment_provider.cancel_payment(self)
                    self.create_log_entry(message="Payment cancelled")
                except NotImplementedError:
                    pass
                except PaymentCancellationFailedError as error:
                    self.create_log_entry(message=f"Failed to cancel payment: {error}")
                except PaymentAlreadyCompletedError as error:
                    self.create_log_entry(message=f"Failed to cancel payment: {error}")
                    raise error

        self.state = new_state

        if new_state == Order.CONFIRMED:
            self.reservation.set_state(Reservation.CONFIRMED, None)
        elif new_state in (Order.REJECTED, Order.EXPIRED, Order.CANCELLED):
            self.reservation.set_state(Reservation.CANCELLED, None)

        if save:
            self.save()

        self.create_log_entry(state_change=new_state, message=log_message)

    def create_log_entry(self, message: str = None, state_change: str = None) -> None:
        OrderLogEntry.objects.create(
            order=self, state_change=state_change or "", message=message or ""
        )

    def get_notification_context(self, language_code):
        with translation.override(language_code):
            return NotificationOrderSerializer(self).data


class OrderLine(models.Model):
    order = models.ForeignKey(
        Order,
        verbose_name=_("order"),
        related_name="order_lines",
        on_delete=models.CASCADE,
    )
    product = models.ForeignKey(
        Product,
        verbose_name=_("product"),
        related_name="order_lines",
        on_delete=models.PROTECT,
    )

    quantity = models.PositiveIntegerField(verbose_name=_("quantity"), default=1)
    unit_price = models.DecimalField(
        verbose_name=_("Unit price including VAT"),
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    total_price = models.DecimalField(
        verbose_name=_("Total price including VAT"),
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    tax_percentage = models.DecimalField(
        verbose_name=_("tax percentage"),
        max_digits=5,
        decimal_places=2,
        default=DEFAULT_TAX_PERCENTAGE,
        choices=[(tax, str(tax)) for tax in TAX_PERCENTAGES],
    )
    price_period = models.DurationField(
        verbose_name=_("price period"),
        null=True,
        blank=True,
        default=timedelta(hours=1),
    )
    price_type = models.CharField(
        max_length=32,
        verbose_name=_("price type"),
        choices=PRICE_TYPE_CHOICES,
        default=PRICE_PER_PERIOD,
    )

    class Meta:
        verbose_name = _("order line")
        verbose_name_plural = _("order lines")
        ordering = ("id",)

    def clean(self):
        if self.price_type == PRICE_PER_PERIOD:
            if not self.price_period:
                raise ValidationError(
                    {
                        "price_period": _(
                            'This field requires a non-zero value when price type is "per period".'  # noqa
                        )
                    }
                )
        else:
            self.price_period = None

    def __str__(self):
        return str(self.product)

    def get_price(self) -> Decimal:
        return self.total_price

    @rounded
    def get_pretax_price(self) -> Decimal:
        return convert_aftertax_to_pretax(self.total_price, self.tax_percentage)


class OrderLogEntry(models.Model):
    order = models.ForeignKey(
        Order,
        verbose_name=_("order log entry"),
        related_name="log_entries",
        on_delete=models.CASCADE,
    )
    timestamp = models.DateTimeField(auto_now_add=True)
    state_change = models.CharField(
        max_length=32,
        verbose_name=_("state change"),
        choices=Order.STATE_CHOICES,
        blank=True,
    )
    message = models.TextField(blank=True)

    class Meta:
        verbose_name = _("order log entry")
        verbose_name_plural = _("order log entries")
        ordering = ("id",)

    def __str__(self):
        return "{} order {} state change {} message {}".format(
            self.timestamp,
            self.order_id,
            self.state_change or None,
            self.message or None,
        )


class LocalizedSerializerField(serializers.Field):
    def __init__(self, *args, **kwargs):
        kwargs["read_only"] = True
        super().__init__(*args, **kwargs)

    def to_representation(self, value):
        return localize(value)


class NotificationProductSerializer(serializers.ModelSerializer):
    id = serializers.ReadOnlyField(source="product_id")
    type_display = serializers.ReadOnlyField(source="get_type_display")

    class Meta:
        model = Product
        fields = ("id", "name", "description", "type", "type_display")


class NotificationOrderLineSerializer(serializers.ModelSerializer):
    product = NotificationProductSerializer()
    price = LocalizedSerializerField(source="get_price")
    unit_price = LocalizedSerializerField()

    class Meta:
        model = OrderLine
        fields = ("product", "quantity", "price", "unit_price")

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        ret["product"]["tax_percentage"] = instance.tax_percentage
        ret["product"]["price_type_display"] = instance.get_price_type_display()
        ret["product"]["price_period_display"] = get_price_period_display(
            instance.price_period
        )
        return ret


class NotificationOrderSerializer(serializers.ModelSerializer):
    id = serializers.ReadOnlyField(source="order_number")
    created_at = LocalizedSerializerField()
    order_lines = NotificationOrderLineSerializer(many=True)
    price = LocalizedSerializerField(source="get_price")

    class Meta:
        model = Order
        fields = ("id", "order_lines", "price", "created_at", "payment_link")
