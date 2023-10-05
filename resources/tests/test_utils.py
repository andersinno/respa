import freezegun

from resources.models.utils import add_days, create_datetime_days_from_now


def test_create_datetime_days_from_now_none():
    assert create_datetime_days_from_now(None) is None


@freezegun.freeze_time("2023-10-5 15:40")
def test_create_datetime_days_from_now_include_extra_day():
    dt = create_datetime_days_from_now(3, exclude_extra_day=False)
    assert dt

    assert dt.year == 2023
    assert dt.month == 10
    assert dt.day == 9

    assert dt.hour == 0
    assert dt.minute == 0


@freezegun.freeze_time("2023-10-5 15:40")
def test_create_datetime_days_from_now_exclude_extra_day():
    dt = create_datetime_days_from_now(3, exclude_extra_day=True)
    assert dt

    assert dt.year == 2023
    assert dt.month == 10
    assert dt.day == 8

    assert dt.hour == 15
    assert dt.minute == 40


@freezegun.freeze_time("2023-10-5 15:40")
def test_add_days_from_start_of_day():
    dt = add_days(3, from_start_of_day=True)

    assert dt.year == 2023
    assert dt.month == 10
    assert dt.day == 8

    assert dt.hour == 0
    assert dt.minute == 0


@freezegun.freeze_time("2023-10-5 15:40")
def test_add_days_from_current_time():
    dt = add_days(3, from_start_of_day=False)

    assert dt.year == 2023
    assert dt.month == 10
    assert dt.day == 8

    assert dt.hour == 15
    assert dt.minute == 40
