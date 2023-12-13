import jsonschema
import requests
from datetime import timedelta
from django.core.exceptions import ValidationError
from django.utils import timezone
from jsonschema.exceptions import ValidationError as JsonSchemaValidationError

from .base import AccessControlDriver


class SecuritasDriver(AccessControlDriver):
    BASE_URL = "https://extapi.flow.securitas.com/v1/"

    SYSTEM_CONFIG_SCHEMA = {
        "type": "object",
        "properties": {
            "api_key": {
                "type": "string",
            },
        },
        "required": ["api_key"],
    }

    RESOURCE_CONFIG_SCHEMA = {
        "type": "object",
        "properties": {
            "uses_pincode": {
                "type": "boolean",
                "default": True,
            },
            "group_id": {"type": "string"},
        },
        "required": ["group_id"],
    }

    DEFAULT_RESOURCE_CONFIG = {
        "uses_pincode": True,
    }

    def install_grant(self, grant):
        self.logger.info("[%s] Installing Securitas grant", grant)

        assert grant.state == grant.INSTALLING

        user = grant.reservation.user

        user_id = str(user.pk)

        access_user, _ = self.system.users.get_or_create(
            identifier=user_id,
            user=user,
        )

        params = {
            "validFrom": grant.starts_at.isoformat(),
            "validTo": grant.ends_at.isoformat(),
        }

        group_id = str(self._get_resource_group_id(grant))

        response = self._api_post(
            "resource-group-access",
            {
                "resourceGroupId": group_id,
                "userExtId": user_id,
                "firstName": user.first_name,
                "lastName": user.last_name,
                "email": user.email,
                "notifyUser": True,
                **params,
            },
        )
        grant.identifier = response.json()["resourceGroupAccessId"]

        # now try and create pincode
        if self.get_resource_setting(grant.resource, "uses_pincode"):
            response = self._api_post(
                "codes",
                {
                    "resourceId": grant.resource.identifier,
                    **params,
                },
            )
            data = response.json()
            grant.access_code = data["code"]
            # save the Securitas ID to driver data so we can delete later
            grant.driver_data = {"code_id": data["id"]}

        grant.user = access_user
        grant.state = grant.INSTALLED
        grant.remove_at = grant.ends_at
        grant.save()

        if grant.access_code:
            grant.notify_access_code()

    def remove_grant(self, grant):
        self.logger.info("[%s] Removing Securitas grant", grant)

        assert grant.state == grant.REMOVING

        # send DELETE for access right and pincode

        self._api_delete(f"resource-group-access/{grant.identifier}")

        if grant.driver_data and "code_id" in grant.driver_data:
            self._api_delete(f"codes/{grant.driver_data['code_id']}")

        grant.state = grant.REMOVED
        grant.removed_at = timezone.now()
        grant.save(update_fields=["state", "removed_at"])

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

    def _api_post(self, endpoint, params=None):
        return self._handle_api_response(
            requests.post(
                self._get_api_endpoint(endpoint),
                **self._get_api_params(params),
            )
        )

    def _api_delete(self, endpoint):
        return self._handle_api_response(
            requests.delete(
                self._get_api_endpoint(endpoint),
                **self._get_api_params(),
            ),
        )

    def _handle_api_response(self, response):
        try:
            try:
                response.raise_for_status()
                return response
            except requests.HTTPError as e:
                if e.response:
                    self.logger.error(e.response.content)
                raise
        except requests.RequestException as e:
            self.logger.exception(e)
            raise

    def _get_api_params(self, params=None):
        return {
            "json": params,
            "headers": {
                "x-api-key": self.get_setting("api_key"),
            },
        }

    def _get_api_endpoint(self, endpoint):
        return self.BASE_URL + endpoint

    def _get_resource_group_id(self, grant):
        try:
            return self.get_resource_setting(grant.resource, "group_id")
        except KeyError:
            raise ValidationError(f"group_id missing for resource #{grant.resource.pk}")
