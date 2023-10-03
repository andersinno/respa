import jsonschema
import requests
from datetime import timedelta
from django.core.exceptions import ValidationError
from django.utils import timezone
from jsonschema.exceptions import ValidationError as JsonSchemaValidationError
from urllib.parse import urljoin

from .base import AccessControlDriver


class SecuritasDriver(AccessControlDriver):
    BASE_URL = "https://extapi.flow.securitas.com/v1"

    SYSTEM_CONFIG_SCHEMA = {
        "type": "object",
        "properties": {
            "api_key": {
                "type": "string",
            },
        },
    }

    RESOURCE_CONFIG_SCHEMA = {
        "type": "object",
        "properties": {
            "resource_id": {
                "type": "string",
            },
            "uses_pincode": {
                "type": "boolean",
                "default": True,
            },
        },
    }

    def get_system_config_schema(self):
        return self.SYSTEM_CONFIG_SCHEMA

    def get_resource_config_schema(self):
        return self.RESOURCE_CONFIG_SCHEMA

    def validate_system_config(self, config):
        try:
            jsonschema.validate(config, self.SYSTEM_CONFIG_SCHEMA)
        except JsonSchemaValidationError as e:
            raise ValidationError(e.message)

    def validate_resource_config(self, resource, config):
        try:
            jsonschema.validate(config, self.RESOURCE_CONFIG_SCHEMA)
        except JsonSchemaValidationError as e:
            raise ValidationError(e.message)

    def install_grant(self, grant):
        self.logger.info("[%s] Installing Securitas grant", grant)

        assert grant.state == grant.INSTALLING

        valid_from = grant.starts_at.isoformat()
        valid_to = grant.ends_at.isoformat()

        resource_id = self.get_setting("resource_id")

        # NOTE: when user is created the first time, we want to create a user in Securitas.
        # this works by passing in userExtId. Subsequent requests should not pass in this param.

        user = grant.reservation.user

        user_id = str(user.pk)

        access_user, created = self.system_users.get_or_create(
            identifier=user_id, user=user
        )

        data = {
            "email": user.email,
            "notifyUser": True,
            "resourceId": resource_id,
            "validFrom": valid_from,
            "validTo": valid_to,
        }

        if not created:
            data["userExtId"] = user_id

        try:
            response = self._api_post("access", data)
        except requests.RequestException:
            access_user.delete()
            raise

        driver_data = {"access": response.json()}
        grant.identifier = driver_data["accessId"]

        # now try and create pincode
        if self.get_setting("uses_pincode"):
            try:
                response = self._api_post(
                    "access",
                    {
                        "resourceId": resource_id,
                        "validFrom": valid_from,
                        "validTo": valid_to,
                    },
                )
            except requests.RequestException as e:
                self.logger.exception(e)

            driver_data = {**driver_data, "code": response.json()}
            grant.access_code = driver_data["code"]["code"]

        grant.driver_data = driver_data
        grant.user = access_user
        grant.state = grant.INSTALLED
        grant.remove_at = grant.ends_at
        grant.save()

        if grant.access_code:
            grant.notify_access_code()

    def remove_grant(self, grant):
        self.logger.info("[%s] Removing Securitas grant", grant)

        assert grant.state == grant.REMOVING

        # send DELETE for access right and user

        self._api_delete(f"access/{grant.identifier}")

        code_data = grant.driver_data.get("code", {})
        code_id = code_data.get("id", None)

        if code_id:
            self._api_delete(f"codes/{code_id}")

        grant.state = grant.REMOVED
        grant.removed_at = timezone.now()
        grant.save()

        self.logger.info(
            "[%s] Securitas access with ID %s and PIN %s removed",
            grant,
            grant.identifier,
            grant.access_code or "NONE",
        )

    def prepare_install_grant(self, grant):
        # Because of a bug in SiPass API, the changes are not synchronized
        # to the building units automatically. We install the grants one day
        # before their start time and schedule a re-install of the units
        # every nightly.
        grant.install_at = grant.starts_at - timedelta(days=1)
        grant.save(update_fields=["install_at"])

    def _api_post(self, endpoint, data=None):
        response = requests.post(
            self._get_endpoint(endpoint),
            **self._get_api_params(data),
        )
        response.raise_for_status()
        return response

    def _api_delete(self, endpoint):
        response = requests.post(
            self._get_endpoint(endpoint),
            **self._get_api_params(),
        )
        response.raise_for_status()
        return response

    def _get_api_params(self, data=None):
        return {
            "json": data,
            "headers": {
                "x-api-key": self.get_setting("api_key"),
            },
        }

    def _get_endpoint(self, endpoint):
        return urljoin(self.BASE_URL, endpoint)
