from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

User = get_user_model()


class SetUserEmailTests(APITestCase):
    def setUp(self):
        # Create a test user
        self.user = User.objects.create_user(
            username="testuser", password="testpassword", email=""
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        EmailAddress.objects.create(user=self.user, email="")

        # Create another user
        self.other_user = User.objects.create_user(
            username="otheruser", password="otherpassword", email="other@example.com"
        )
        EmailAddress.objects.create(user=self.other_user, email="other@example.com")

    def test_set_email_success(self):
        url = reverse("user-set-email", kwargs={"pk": self.user.pk})
        data = {"email": "newemail@example.com"}

        response = self.client.post(url, data, format="json")

        self.user.refresh_from_db()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {"detail": "Email set successfully."})
        self.assertEqual(self.user.email, "newemail@example.com")
        self.assertTrue(
            EmailAddress.objects.filter(
                user=self.user, email="newemail@example.com"
            ).exists()
        )

    def test_set_email_already_set(self):
        # Set an email for the user first
        self.user.email = "existingemail@example.com"
        self.user.save()

        url = reverse("user-set-email", kwargs={"pk": self.user.pk})
        data = {"email": "anotheremail@example.com"}

        response = self.client.post(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data, {"detail": "User already has an email set."})
        self.assertEqual(self.user.email, "existingemail@example.com")

    def test_set_email_not_provided(self):
        url = reverse("user-set-email", kwargs={"pk": self.user.pk})
        data = {"email": ""}  # No email in the data

        response = self.client.post(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data, {"detail": "Email address is required."})
        self.assertEqual(self.user.email, "")

    def test_set_email_already_in_use(self):
        url = reverse("user-set-email", kwargs={"pk": self.user.pk})
        data = {"email": "other@example.com"}  # Email already used by other_user

        response = self.client.post(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data, {"detail": "The email address is already in use."}
        )
        self.assertEqual(self.user.email, "")
