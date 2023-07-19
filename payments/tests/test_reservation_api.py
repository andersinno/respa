import pytest
from guardian.shortcuts import assign_perm
from rest_framework.exceptions import ErrorDetail
from rest_framework.reverse import reverse
from unittest.mock import MagicMock, create_autospec, patch
from urllib.parse import urlencode

from notifications.tests.utils import check_received_mail_exists
from resources.enums import UnitAuthorizationLevel
from resources.models import Reservation
from resources.models.unit import UnitAuthorization
from resources.tests.conftest import resource_in_unit  # noqa
from resources.tests.conftest import staff_api_client  # noqa
from resources.tests.conftest import user_api_client  # noqa
from resources.tests.test_reservation_api import day_and_period  # noqa
from respa_pricing.tests.factories import (
    PricedProductFactory,
    PriceListFactory,
    UserGroupFactory,
    UserGroupPriceListItemFactory,
)

from ..factories import OrderWithOrderLinesFactory, ProductFactory
from ..models import Order, Product
from ..providers.base import PaymentProvider
from .test_notifications import paid_reservation_approved_notification  # noqa
from .test_notifications import paid_reservation_approved_official_notification  # noqa
from .test_order_api import ORDER_LINE_FIELDS, PRODUCT_FIELDS

LIST_URL = reverse("reservation-list")

ORDER_FIELDS = {"id", "state", "price", "order_lines"}


def get_detail_url(reservation):
    return reverse("reservation-detail", kwargs={"pk": reservation.pk})


def build_reservation_data(resource):
    return {
        "resource": resource.pk,
        "begin": "2115-04-04T11:00:00+02:00",
        "end": "2115-04-04T12:00:00+02:00",
    }


def build_order_data(
    product, quantity=None, product_2=None, quantity_2=None, unit_price=10.00
):
    price_list = PriceListFactory()
    price_list_2 = PriceListFactory()
    user_group = UserGroupFactory()

    for pl in [price_list, price_list_2]:
        UserGroupPriceListItemFactory(
            price_list=pl,
            user_group=user_group,
            price=unit_price,
        )

    PricedProductFactory(product=product, price_list=price_list)

    if product_2 and product_2 != product:
        PricedProductFactory(product=product_2, price_list=price_list_2)
    data = {
        "order_lines": [
            {
                "product": product.product_id,
                "unit_price": unit_price,
                "user_group": user_group.id,
            }
        ],
        "return_url": "https://varauspalvelu.com/payment_return_url/",
    }

    if quantity:
        data["order_lines"][0]["quantity"] = quantity

    if product_2:
        order_line_data = {
            "product": product_2.product_id,
            "unit_price": unit_price,
            "user_group": user_group.id,
        }
        if quantity_2:
            order_line_data["quantity"] = quantity_2
        data["order_lines"].append(order_line_data)

    return data


@pytest.fixture(autouse=True)
def auto_use_django_db(db):
    pass


@pytest.fixture
def product(resource_in_unit):
    return ProductFactory(resources=[resource_in_unit])


@pytest.fixture
def product_2(resource_in_unit):
    return ProductFactory(resources=[resource_in_unit])


@pytest.fixture
def paid_resource(resource_in_unit):
    resource_in_unit.free_to_use = False
    resource_in_unit.save(update_fields=["free_to_use"])
    return resource_in_unit


def make_mock_provider():
    mocked_provider = create_autospec(PaymentProvider)
    mocked_provider.initiate_payment = MagicMock(
        return_value="https://mocked-payment-url.com"
    )
    return mocked_provider


@pytest.fixture(autouse=True)
def mock_provider():
    mocked_provider = make_mock_provider()

    with patch(
        "payments.api.reservation.get_payment_provider", return_value=mocked_provider
    ):
        yield mocked_provider


@pytest.mark.parametrize(
    "has_order, free_to_use, expected_state, new_orders",
    (
        (False, False, Reservation.CONFIRMED, 0),
        (False, True, Reservation.CONFIRMED, 0),
        (True, False, Reservation.WAITING_FOR_PAYMENT, 1),
        (True, True, Reservation.CONFIRMED, 0),
    ),
)
def test_reservation_creation_state(
    user_api_client,
    resource_in_unit,
    has_order,
    free_to_use,
    expected_state,
    new_orders,
):
    resource_in_unit.free_to_use = free_to_use
    resource_in_unit.save()

    reservation_data = build_reservation_data(resource_in_unit)
    if has_order:
        product = ProductFactory(type=Product.RENT, resources=[resource_in_unit])
        reservation_data["order"] = build_order_data(product)

    response = user_api_client.post(LIST_URL, reservation_data)

    assert response.status_code == 201
    new_reservation = Reservation.objects.last()
    assert new_reservation.state == expected_state

    assert Order.objects.count() == new_orders


@pytest.mark.parametrize(
    "has_order, free_to_use, expected_state, new_orders",
    (
        (False, False, Reservation.REQUESTED, 0),
        (False, True, Reservation.REQUESTED, 0),
        (True, False, Reservation.REQUESTED, 1),
        (True, True, Reservation.REQUESTED, 0),
    ),
)
def test_reservation_creation_state_need_manual_confirmation(
    user_api_client,
    resource_in_unit,
    has_order,
    free_to_use,
    expected_state,
    new_orders,
):
    resource_in_unit.free_to_use = free_to_use
    resource_in_unit.need_manual_confirmation = True
    resource_in_unit.save()

    reservation_data = build_reservation_data(resource_in_unit)
    if has_order:
        product = ProductFactory(type=Product.RENT, resources=[resource_in_unit])
        reservation_data["order"] = build_order_data(product)

    response = user_api_client.post(LIST_URL, reservation_data)

    assert response.status_code == 201
    new_reservation = Reservation.objects.last()
    assert new_reservation.state == expected_state

    assert Order.objects.count() == new_orders


def test_reservation_creation_state_total_price_zero(user_api_client, resource_in_unit):
    """If total price of order is zero, no payment is required.

    Reservation should be CONFIRMED and no orders should be created.
    """
    reservation_data = build_reservation_data(resource_in_unit)
    product = ProductFactory(type=Product.RENT, resources=[resource_in_unit])
    reservation_data["order"] = build_order_data(product, unit_price=0)

    response = user_api_client.post(LIST_URL, reservation_data)

    assert response.status_code == 201
    new_reservation = Reservation.objects.last()

    assert new_reservation.state == Reservation.CONFIRMED
    assert Order.objects.count() == 0


@pytest.mark.django_db
def test_payment_return_url_is_required_when_updating_state_to_waiting_for_payment(
    api_client, general_admin, requested_reservation_with_order
):
    reservation = requested_reservation_with_order
    reservation.state = Reservation.REQUESTED
    reservation.save()
    data = build_reservation_data(reservation.resource)
    data["state"] = Reservation.WAITING_FOR_PAYMENT
    assign_perm(
        "unit:can_approve_reservation",
        general_admin,
        reservation.resource.unit,
    )
    assign_perm(
        "unit:can_modify_paid_reservations",
        general_admin,
        reservation.resource.unit,
    )
    api_client.force_authenticate(user=general_admin)
    expected_error = ErrorDetail(
        string="Return URL is required to initiate the payment", code="invalid"
    )

    response = api_client.put(get_detail_url(reservation), data=data)
    assert response.status_code == 400
    assert response.data[0] == expected_error


@pytest.mark.parametrize("endpoint", ("list", "detail"))
@pytest.mark.parametrize(
    "include",
    (None, "", "foo", ["foo", "bar"], "order_detail", ["foo", "order_detail"]),
)
def test_reservation_orders_field(
    user_api_client, order_with_products, endpoint, include
):
    url = (
        LIST_URL
        if endpoint == "list"
        else get_detail_url(order_with_products.reservation)
    )
    if include is not None:
        if not isinstance(include, list):
            include = list(include)
        query_string = urlencode([("include", i) for i in include])
        url += "?" + query_string

    response = user_api_client.get(url)
    assert response.status_code == 200

    reservation_data = (
        response.data["results"][0] if endpoint == "list" else response.data
    )

    order_data = reservation_data["order"]
    if include is not None and "order_detail" in include:
        # order should be nested data
        assert set(order_data.keys()) == ORDER_FIELDS
        assert order_data["id"] == order_with_products.order_number
        for ol in order_data["order_lines"]:
            assert set(ol.keys()) == ORDER_LINE_FIELDS
            assert set(ol["product"]) == PRODUCT_FIELDS
    else:
        # order should be just ID
        assert order_data == order_with_products.order_number


@pytest.mark.parametrize("endpoint", ("list", "detail"))
@pytest.mark.parametrize(
    "request_user, expected",
    (
        (None, False),
        ("owner", True),
        ("other", False),
        ("other_with_perm", True),
    ),
)
def test_reservation_order_field_visibility(
    api_client, order_with_products, user2, request_user, endpoint, expected
):
    url = (
        LIST_URL
        if endpoint == "list"
        else get_detail_url(order_with_products.reservation)
    )

    if request_user == "owner":
        api_client.force_authenticate(user=order_with_products.reservation.user)
    elif request_user == "other":
        api_client.force_authenticate(user=user2)
    elif request_user == "other_with_perm":
        assign_perm(
            "unit:can_view_reservation_product_orders",
            user2,
            order_with_products.reservation.resource.unit,
        )
        api_client.force_authenticate(user=user2)

    response = api_client.get(url)
    assert response.status_code == 200

    reservation_data = (
        response.data["results"][0] if endpoint == "list" else response.data
    )
    assert ("order" in reservation_data) is expected


def test_reservation_in_state_waiting_for_payment_cannot_be_modified_or_deleted(
    user_api_client, order_with_products
):
    reservation = order_with_products.reservation
    response = user_api_client.put(
        get_detail_url(reservation), data=build_reservation_data(reservation.resource)
    )
    assert response.status_code == 403

    response = user_api_client.delete(get_detail_url(reservation))
    assert response.status_code == 403


@pytest.mark.parametrize("has_perm", (False, True))
def test_reservation_that_has_order_cannot_be_modified_without_permission(
    user_api_client, order_with_products, user, has_perm
):
    order_with_products.set_state(Order.CONFIRMED)
    if has_perm:
        assign_perm(
            "unit:can_modify_paid_reservations",
            user,
            order_with_products.reservation.resource.unit,
        )

    data = build_reservation_data(order_with_products.reservation.resource)
    response = user_api_client.put(
        get_detail_url(order_with_products.reservation), data=data
    )
    assert response.status_code == 200 if has_perm else 403

    response = user_api_client.delete(get_detail_url(order_with_products.reservation))
    assert response.status_code == 204 if has_perm else 403


def test_order_post(user_api_client, paid_resource, product, product_2, mock_provider):
    reservation_data = build_reservation_data(paid_resource)
    reservation_data["order"] = build_order_data(
        product=product, product_2=product_2, quantity_2=5
    )

    response = user_api_client.post(LIST_URL, reservation_data)

    assert response.status_code == 201, response.data
    mock_provider.initiate_payment.assert_called()

    # check response fields
    order_create_response_fields = ORDER_FIELDS.copy() | {"payment_url"}
    order_data = response.data["order"]
    assert set(order_data.keys()) == order_create_response_fields
    assert order_data["payment_url"].startswith("https://mocked-payment-url.com")

    # check created object
    new_order = Order.objects.last()
    assert new_order.reservation == Reservation.objects.last()

    # check order lines
    order_lines = new_order.order_lines.all()
    assert order_lines.count() == 2
    assert order_lines[0].product == product
    assert order_lines[0].quantity == 1
    assert order_lines[1].product == product_2
    assert order_lines[1].quantity == 5


def test_order_product_must_match_resource(
    user_api_client, product, paid_resource, resource_in_unit2
):
    product_with_another_resource = ProductFactory(resources=[resource_in_unit2])
    data = build_reservation_data(paid_resource)
    data["order"] = build_order_data(
        product=product, product_2=product_with_another_resource
    )

    response = user_api_client.post(LIST_URL, data)

    assert response.status_code == 400
    assert "product" in response.data["order"]["order_lines"][1]


def test_order_line_products_are_unique(user_api_client, paid_resource, product):
    """Test order validator enforces that order lines cannot contain duplicates of the same product"""

    reservation_data = build_reservation_data(paid_resource)
    reservation_data["order"] = build_order_data(
        product, quantity=2, product_2=product, quantity_2=2
    )
    response = user_api_client.post(LIST_URL, reservation_data)

    assert response.status_code == 400


@pytest.mark.parametrize("has_rent", (True, False))
def test_rent_product_makes_order_required_(user_api_client, paid_resource, has_rent):
    reservation_data = build_reservation_data(paid_resource)
    if has_rent:
        prod = ProductFactory(type=Product.RENT, resources=[paid_resource])
        prod.resources.update(free_to_use=False)

    response = user_api_client.post(LIST_URL, reservation_data)

    if has_rent:
        assert response.status_code == 400
        assert "order" in response.data
    else:
        assert response.status_code == 201


@pytest.mark.parametrize("free_to_use", (True, False))
def test_not_free_to_use_makes_order_required(
    user_api_client, resource_in_unit, free_to_use
):
    reservation_data = build_reservation_data(resource_in_unit)
    prod = ProductFactory(type=Product.RENT, resources=[resource_in_unit])
    prod.resources.update(free_to_use=free_to_use)

    response = user_api_client.post(LIST_URL, reservation_data)

    if not free_to_use:
        assert response.status_code == 400
        assert "order" in response.data
    else:
        assert response.status_code == 201


def test_order_cannot_be_modified(user_api_client, order_with_products, user):
    order_with_products.set_state(Order.CONFIRMED)
    assert order_with_products.reservation.state == Reservation.CONFIRMED
    new_product = ProductFactory(resources=[order_with_products.reservation.resource])
    reservation_data = build_reservation_data(order_with_products.reservation.resource)
    reservation_data["order"] = {
        "order_lines": [{"product": new_product.product_id, "quantity": 777}],
        "return_url": "https://foo",
    }
    assign_perm(
        "unit:can_modify_paid_reservations",
        user,
        order_with_products.reservation.resource.unit,
    )

    response = user_api_client.put(
        get_detail_url(order_with_products.reservation), reservation_data
    )

    assert response.status_code == 200, response.data
    order_with_products.refresh_from_db()
    assert order_with_products.order_lines.first().product != new_product
    assert order_with_products.order_lines.first().quantity != 777
    assert order_with_products.order_lines.count() > 1


def test_extra_product_doesnt_make_order_required(user_api_client, paid_resource):
    reservation_data = build_reservation_data(paid_resource)
    ProductFactory(type=Product.EXTRA, resources=[paid_resource])

    response = user_api_client.post(LIST_URL, reservation_data)

    assert response.status_code == 201


def test_order_must_include_rent_if_one_exists(user_api_client, paid_resource):
    reservation_data = build_reservation_data(paid_resource)
    ProductFactory(type=Product.RENT, resources=[paid_resource])
    extra = ProductFactory(type=Product.EXTRA, resources=[paid_resource])
    reservation_data["order"] = build_order_data(product=extra)

    response = user_api_client.post(LIST_URL, reservation_data)
    assert response.status_code == 400


@pytest.mark.parametrize(
    "reservation_type,level,has_order,success,new_state,num_orders",
    (
        # NORMAL, no authorization, has order, OK+payment
        (Reservation.TYPE_NORMAL, None, True, True, Reservation.WAITING_FOR_PAYMENT, 1),
        # INTERNAL USE, no authorization, has order, FAIL
        (Reservation.TYPE_INTERNAL_USE, None, True, False, None, 0),
        # NORMAL, no authorization, no order, FAIL
        (Reservation.TYPE_NORMAL, None, False, False, None, 0),
        # INTERNAL USE, no authorization, no order, FAIL
        (Reservation.TYPE_INTERNAL_USE, None, False, False, None, 0),
        # NORMAL, viewer, has order, OK+payment
        (
            Reservation.TYPE_NORMAL,
            UnitAuthorizationLevel.viewer,
            True,
            True,
            Reservation.WAITING_FOR_PAYMENT,
            1,
        ),
        # INTERNAL USE, viewer, has order, FAIL
        (
            Reservation.TYPE_INTERNAL_USE,
            UnitAuthorizationLevel.viewer,
            True,
            False,
            None,
            0,
        ),
        # NORMAL, viewer, no order, FAIL
        (Reservation.TYPE_NORMAL, UnitAuthorizationLevel.viewer, False, False, None, 0),
        # INTERNAL USE, viewer, no order, FAIL
        (
            Reservation.TYPE_INTERNAL_USE,
            UnitAuthorizationLevel.viewer,
            False,
            False,
            None,
            0,
        ),
        # NORMAL, manager, has order, OK+payment
        (
            Reservation.TYPE_NORMAL,
            UnitAuthorizationLevel.manager,
            True,
            True,
            Reservation.WAITING_FOR_PAYMENT,
            1,
        ),
        # NORMAL, manager, no order, FAIL
        (
            Reservation.TYPE_NORMAL,
            UnitAuthorizationLevel.manager,
            False,
            False,
            None,
            0,
        ),
        # INTERNAL USE, manager, no order, OK+confirmed
        (
            Reservation.TYPE_INTERNAL_USE,
            UnitAuthorizationLevel.manager,
            False,
            True,
            Reservation.CONFIRMED,
            0,
        ),
        # NORMAL, admin, has order, OK+payment
        (
            Reservation.TYPE_NORMAL,
            UnitAuthorizationLevel.admin,
            True,
            True,
            Reservation.WAITING_FOR_PAYMENT,
            1,
        ),
        # NORMAL, admin, no order, FAIL
        (
            Reservation.TYPE_NORMAL,
            UnitAuthorizationLevel.admin,
            False,
            False,
            None,
            0,
        ),
        # INTERNAL USE, admin, no order, OK+confirmed
        (
            Reservation.TYPE_INTERNAL_USE,
            UnitAuthorizationLevel.admin,
            False,
            True,
            Reservation.CONFIRMED,
            0,
        ),
    ),
)
def test_user_may_bypass_payment_on_paid_resource(
    user_api_client,
    paid_resource,
    mock_provider,
    user,
    reservation_type,
    level,
    has_order,
    success,
    new_state,
    num_orders,
):
    """Checks that certain users bypass order processing and payment
    if granted specific authorizations on the resource.
    """
    reservation_data = build_reservation_data(paid_resource)
    reservation_data["type"] = reservation_type

    product = ProductFactory(type=Product.RENT, resources=[paid_resource])

    if has_order:
        reservation_data["order"] = build_order_data(product)

    if level:
        UnitAuthorization.objects.create(
            subject=paid_resource.unit,
            level=level,
            authorized=user,
        )
    response = user_api_client.post(LIST_URL, reservation_data)

    if success:
        assert response.status_code == 201

        new_reservation = Reservation.objects.last()
        assert new_reservation.type == reservation_type
        assert new_reservation.state == new_state

    else:
        assert response.status_code == 400
        assert Reservation.objects.count() == 0

    assert Order.objects.count() == num_orders

    if num_orders:
        mock_provider.initiate_payment.assert_called()


@pytest.mark.django_db
def test_approve_paid_reservation(
    mailoutbox,
    settings,
    paid_reservation_approved_notification,
    paid_reservation_approved_official_notification,
    staff_api_client,
    paid_resource,
    staff_user,
    user,
):
    """When a paid reservation is approved:

    1. Reservation new state should be WAITING_FOR_PAYMENT
    2. Payment is initiated
    3. Payment link is emailed to customer
    """

    settings.RESPA_MAILS_ENABLED = True

    paid_resource.need_manual_confirmation = True

    paid_resource.save()

    assign_perm(
        "unit:can_approve_reservation",
        staff_user,
        paid_resource.unit,
    )

    assign_perm(
        "unit:can_modify_paid_reservations",
        staff_user,
        paid_resource.unit,
    )

    reservation_data = build_reservation_data(paid_resource)

    reservation = Reservation.objects.create(
        state=Reservation.REQUESTED,
        user=user,
        resource=paid_resource,
        begin=reservation_data["begin"],
        end=reservation_data["end"],
    )

    OrderWithOrderLinesFactory(
        reservation=reservation,
        state=Order.WAITING,
        payment_link="https://random-payment-link.com",
    )

    payment_return_url = "https://tampere.varaamo.fi/payment-done/"
    #
    # provider is in ReservationViewSet.perform_update
    mocked_provider = make_mock_provider()

    with patch(
        "resources.api.reservation.get_payment_provider", return_value=mocked_provider
    ):
        response = staff_api_client.put(
            get_detail_url(reservation),
            {
                "state": Reservation.WAITING_FOR_PAYMENT,
                "payment_return_url": payment_return_url,
                **reservation_data,
            },
        )

    assert response.status_code == 200

    reservation.refresh_from_db()

    assert reservation.approved_at
    assert reservation.state == Reservation.WAITING_FOR_PAYMENT

    mocked_provider.initiate_payment.assert_called()

    # check notification sent
    assert len(mailoutbox) == 2

    check_received_mail_exists(
        "Paid reservation approved subject.",
        user.email,
        "Paid reservation approved body.",
        clear_outbox=False,
    )

    check_received_mail_exists(
        "Paid reservation approved official subject.",
        staff_user.email,
        "Paid reservation approved official body.",
    )
