from django.contrib import admin

from .models import (
    AccessControlGrant,
    AccessControlResource,
    AccessControlSystem,
    AccessControlUser,
)


@admin.register(AccessControlSystem)
class AccessControlSystemAdmin(admin.ModelAdmin):
    pass


@admin.register(AccessControlResource)
class AccessControlResourceAdmin(admin.ModelAdmin):
    list_display = (
        "resource",
        "system",
        "driver_identifier",
        "active_grant_count",
    )

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related(
                "resource",
                "resource__unit",
                "system",
            )
        )

    raw_id_fields = ("resource",)


@admin.register(AccessControlUser)
class AccessControlUserAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "state",
        "system",
    )

    list_filter = ("state",)

    raw_id_fields = ("user",)

    search_fields = (
        "first_name",
        "last_name",
        "user__email",
        "user__first_name",
        "user__last_name",
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("user", "system")


@admin.register(AccessControlGrant)
class AccessControlGrantAdmin(admin.ModelAdmin):
    list_display = (
        "email",
        "state",
        "resource",
        "starts_at",
        "ends_at",
        "access_code",
        "identifier",
    )

    list_filter = ("state",)

    search_fields = (
        "user__user__email",
        "user__first_name",
        "user__last_name",
    )

    raw_id_fields = (
        "user",
        "reservation",
        "resource",
    )

    def email(self, obj):
        return obj.user.user.email if obj.user else "-"

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related(
                "resource",
                "resource__resource",
                "resource__resource__unit",
                "resource__system",
                "user",
                "user__user",
            )
        )
