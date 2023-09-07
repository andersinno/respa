import pytest

from resources.tests.conftest import *

from ..models import RespaInstruction


@pytest.fixture()
def user_instructions():
    return RespaInstruction.objects.create(
        active=True,
        order=1,
        applicable_for="user",
        content_fi="<h1>Ohjeet</h1>",
        content_en="<h1>Instructions</h1>",
    )


@pytest.fixture()
def admin_instructions():
    return RespaInstruction.objects.create(
        active=True,
        order=1,
        applicable_for="admin",
        content_fi="<h1>Ylläpitäjän ohjeet</h1>",
        content_en="<h1>Admin instructions</h1>",
    )
