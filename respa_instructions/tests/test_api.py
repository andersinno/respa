import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_user_instructions_list(api_client, user_instructions, admin_instructions):
    url = reverse("user_instructions-list")

    response = api_client.get(url)

    assert response.status_code == 200
    assert len(response.data["results"]) == 1
    data = response.data["results"][0]
    assert "<h1>Ohjeet</h1>" in data["content"]["fi"]
    assert "<h1>Instructions</h1>" in data["content"]["en"]


@pytest.mark.django_db
def test_admin_instructions_list(
    api_client, user_instructions, admin_instructions, user, staff_user
):
    url = reverse("admin_instructions-list")

    # Regular users should get permission denied.
    api_client.force_authenticate(user=user)
    response = api_client.get(url)
    assert response.status_code == 403

    # Try again with a staff user.
    api_client.force_authenticate(user=staff_user)
    response = api_client.get(url)
    assert response.status_code == 200
    assert len(response.data["results"]) == 1
    data = response.data["results"][0]
    assert "<h1>Ylläpitäjän ohjeet</h1>" in data["content"]["fi"]
    assert "<h1>Admin instructions</h1>" in data["content"]["en"]
