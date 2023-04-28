# -*- coding: utf-8 -*-
import datetime
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.utils.translation import activate
from PIL import Image

from resources.enums import UnitAuthorizationLevel
from resources.errors import InvalidImage
from resources.models import Resource, ResourceImage
from resources.tests.utils import (
    create_resource_image,
    get_field_errors,
    get_test_image_data,
)
from respa_pricing.tests.factories import (
    EventTypePriceListItemFactory,
    PricedProductFactory,
    UserGroupPriceListItemFactory,
)


@pytest.fixture
def priced_product(space_resource):
    return PricedProductFactory(product__resources=[space_resource])


@pytest.fixture
def space_resource_with_product(priced_product, space_resource):
    return space_resource


@pytest.mark.django_db
def test_free_of_charge_free_to_use_true_no_pricing_info(space_resource):
    space_resource.free_to_use = True
    space_resource.save()

    assert Resource.objects.free_of_charge(True).count() == 1
    assert Resource.objects.free_of_charge(False).count() == 0


@pytest.mark.django_db
def test_free_of_charge_free_to_use_false_no_pricing_info(space_resource):
    """Even if free_to_use is False, is still free of charge as there is
    no pricing info attached."""

    space_resource.free_to_use = False
    space_resource.save()

    assert Resource.objects.free_of_charge(True).count() == 1
    assert Resource.objects.free_of_charge(False).count() == 0


@pytest.mark.django_db
def test_free_of_charge_free_to_use_true_with_pricing_info(
    space_resource_with_product, priced_product
):
    """Even if resource has pricing info attached, if free_to_use is True
    then will assume free of charge."""

    UserGroupPriceListItemFactory(price_list=priced_product.price_list, price="100.00")

    space_resource_with_product.free_to_use = True
    space_resource_with_product.save()

    assert Resource.objects.free_of_charge(True).count() == 1
    assert Resource.objects.free_of_charge(False).count() == 0


@pytest.mark.django_db
def test_free_of_charge_free_to_use_false_with_pricing_info_zero(
    space_resource_with_product, priced_product
):
    """If pricing is available but is zero, then should still be free of charge."""
    UserGroupPriceListItemFactory(price_list=priced_product.price_list, price="00.00")

    space_resource_with_product.free_to_use = False
    space_resource_with_product.save()

    assert Resource.objects.free_of_charge(True).count() == 1
    assert Resource.objects.free_of_charge(False).count() == 0


@pytest.mark.django_db
def test_free_of_charge_free_to_use_false_with_user_group_pricing_info(
    space_resource_with_product, priced_product
):
    UserGroupPriceListItemFactory(price_list=priced_product.price_list, price="100.00")

    space_resource_with_product.free_to_use = False
    space_resource_with_product.save()

    assert Resource.objects.free_of_charge(True).count() == 0
    assert Resource.objects.free_of_charge(False).count() == 1


@pytest.mark.django_db
def test_free_of_charge_free_to_use_false_with_event_type_pricing_info(
    space_resource_with_product, priced_product
):
    EventTypePriceListItemFactory(price_list=priced_product.price_list, price="100.00")

    space_resource_with_product.free_to_use = False
    space_resource_with_product.save()

    assert Resource.objects.free_of_charge(True).count() == 0
    assert Resource.objects.free_of_charge(False).count() == 1


@pytest.mark.django_db
def test_free_of_charge_free_to_use_false_with_mixed_pricing_info(
    space_resource_with_product, priced_product
):
    """Check combination of different prices"""
    UserGroupPriceListItemFactory(price_list=priced_product.price_list, price="0.00")
    UserGroupPriceListItemFactory(price_list=priced_product.price_list, price="5.00")
    EventTypePriceListItemFactory(price_list=priced_product.price_list, price="100.00")

    space_resource_with_product.free_to_use = False
    space_resource_with_product.save()

    assert Resource.objects.free_of_charge(True).count() == 0
    assert Resource.objects.free_of_charge(False).count() == 1


@pytest.mark.django_db
def test_with_pricing_no_pricing_info(space_resource):
    """If no user group or event type pricing, max/min price should be None."""
    resource = Resource.objects.with_pricing().first()

    assert resource.min_price is None
    assert resource.max_price is None


@pytest.mark.django_db
def test_with_pricing_user_groups_only(space_resource_with_product, priced_product):
    UserGroupPriceListItemFactory(price_list=priced_product.price_list, price="100.00")
    UserGroupPriceListItemFactory(price_list=priced_product.price_list, price="200.00")

    resource = Resource.objects.with_pricing().first()

    assert resource.min_price == Decimal("100.00")
    assert resource.max_price == Decimal("200.00")


@pytest.mark.django_db
def test_with_pricing_event_type_price_only(
    space_resource_with_product, priced_product
):
    EventTypePriceListItemFactory(price_list=priced_product.price_list, price="100.00")
    EventTypePriceListItemFactory(price_list=priced_product.price_list, price="200.00")

    resource = Resource.objects.with_pricing().first()

    assert resource.min_price == Decimal("100.00")
    assert resource.max_price == Decimal("200.00")


@pytest.mark.django_db
def test_with_pricing_mixed_user_group_and_event_type(
    space_resource_with_product, priced_product
):
    UserGroupPriceListItemFactory(price_list=priced_product.price_list, price="100.00")
    UserGroupPriceListItemFactory(price_list=priced_product.price_list, price="150.00")
    EventTypePriceListItemFactory(price_list=priced_product.price_list, price="120.00")
    EventTypePriceListItemFactory(price_list=priced_product.price_list, price="200.00")

    resource = Resource.objects.with_pricing().first()

    assert resource.min_price == Decimal("100.00")
    assert resource.max_price == Decimal("200.00")


@pytest.mark.django_db
def test_only_one_main_image(space_resource):
    i1 = create_resource_image(space_resource, type="main")
    assert i1.type == "main"
    i2 = create_resource_image(space_resource, type="main")

    assert i2.type == "main"
    # The first image should have been turned non-main after
    # the new main image was created
    assert ResourceImage.objects.get(pk=i1.pk).type == "other"

    i3 = create_resource_image(space_resource, type="other")
    assert i3.type == "other"
    # But adding a new non-main image should not have dethroned i2 from being main
    assert ResourceImage.objects.get(pk=i2.pk).type == "main"


@pytest.mark.django_db
@pytest.mark.parametrize("format", ("BMP", "PCX"))
@pytest.mark.parametrize("image_type", ("main", "map", "ground_plan"))
def test_image_transcoding(space_resource, format, image_type):
    """
    Test that images get transcoded into JPEG or PNG if they're not JPEG/PNG
    """
    data = get_test_image_data(format=format)
    ri = ResourceImage(
        resource=space_resource,
        sort_order=8,
        type=image_type,
        image=ContentFile(data, name="long_horse.%s" % format),
    )
    expected_format = "PNG" if image_type in ("map", "ground_plan") else "JPEG"
    ri.full_clean()
    assert ri.image_format == expected_format  # Transcoding occurred
    assert Image.open(ri.image).format == expected_format  # .. it really did!


@pytest.mark.django_db
@pytest.mark.parametrize("format", ("JPEG", "PNG"))
def test_image_transcoding_bypass(space_resource, format):
    """
    Test that JPEGs and PNGs bypass transcoding
    """
    data = get_test_image_data(format=format)
    ri = ResourceImage(
        resource=space_resource,
        sort_order=8,
        type="main",
        image=ContentFile(data, name="nice.%s" % format),
    )
    ri.full_clean()
    assert ri.image_format == format  # Transcoding did not occur
    assert Image.open(ri.image).format == format  # no, no transcoding
    ri.image.seek(0)  # PIL may have `seek`ed or read the stream
    assert ri.image.read() == data  # the bitstream is identical


@pytest.mark.django_db
def test_invalid_image(space_resource):
    data = b"this is text, not an image!"
    ri = ResourceImage(
        resource=space_resource,
        sort_order=8,
        type="main",
        image=ContentFile(data, name="bogus.xyz"),
    )
    with pytest.raises(InvalidImage) as ei:
        ri.full_clean()
    assert "cannot identify" in ei.value.message


@pytest.mark.django_db
def test_time_slot_validations(resource_in_unit):
    activate("en")

    resource_in_unit.min_period = datetime.timedelta(hours=2)
    resource_in_unit.slot_size = datetime.timedelta(minutes=45)
    with pytest.raises(ValidationError) as error:
        resource_in_unit.full_clean()
    assert "This value must be a multiple of slot_size" in get_field_errors(
        error.value, "min_period"
    )

    resource_in_unit.min_period = datetime.timedelta(hours=2)
    resource_in_unit.slot_size = datetime.timedelta(minutes=30)
    resource_in_unit.full_clean()


@pytest.mark.django_db
def test_queryset_with_perm(resource_in_unit, user):
    resources = Resource.objects.with_perm("can_view_reservation_catering_orders", user)
    assert not resources

    user.unit_authorizations.create(
        authorized=user,
        level=UnitAuthorizationLevel.manager,
        subject=resource_in_unit.unit,
    )
    user.save()

    resources = Resource.objects.with_perm("can_view_reservation_catering_orders", user)
    assert resources
    assert resource_in_unit in resources

    user.unit_authorizations.create(
        authorized=user,
        level=UnitAuthorizationLevel.admin,
        subject=resource_in_unit.unit,
    )

    resources = Resource.objects.with_perm("can_modify_paid_reservations", user)
    assert not resources

    user.unit_authorizations.all().delete()

    user.unit_authorizations.create(
        authorized=user,
        level=UnitAuthorizationLevel.viewer,
        subject=resource_in_unit.unit,
    )

    resources = Resource.objects.with_perm("can_modify_reservations", user)
    assert resources
    assert resource_in_unit in resources
