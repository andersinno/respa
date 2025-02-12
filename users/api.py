from allauth.socialaccount.models import EmailAddress
from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework import permissions, serializers, generics, viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response

from resources.models.utils import build_ical_feed_url
from resources.models import Unit
from .utils import get_user_auth_backend

all_views = []


def register_view(klass, name, base_name=None):
    entry = {'class': klass, 'name': name}
    if base_name is not None:
        entry['base_name'] = base_name
    all_views.append(entry)


class UserSerializer(serializers.ModelSerializer):
    display_name = serializers.ReadOnlyField(source='get_display_name')
    ical_feed_url = serializers.SerializerMethodField()
    staff_perms = serializers.SerializerMethodField()
    login_method = serializers.SerializerMethodField()

    class Meta:
        fields = [
            'last_login', 'username', 'email', 'date_joined',
            'first_name', 'last_name', 'uuid', 'department_name',
            'is_staff', 'display_name', 'ical_feed_url', 'staff_perms', 'favorite_resources',
            'login_method',
        ]
        model = get_user_model()

    def get_ical_feed_url(self, obj):
        return build_ical_feed_url(obj.get_or_create_ical_token(), self.context['request'])

    def get_staff_perms(self, obj):
        perm_objs = obj.userobjectpermission_set.all()
        perms = {}
        # We support only units for now
        for p in perm_objs:
            if p.content_type.model_class() != Unit:
                continue
            obj_perms = perms.setdefault(p.object_pk, [])
            perm_name = p.permission.codename
            if perm_name.startswith('unit:'):
                perm_name = perm_name[5:]
            obj_perms.append(perm_name)
        if not perms:
            return {}
        return {'unit': perms}

    def get_login_method(self, obj):
        auth = self.context['request'].auth
        if not auth:
            return None
        try:
            return get_user_auth_backend(self.context['request'])
        except Exception as e:
            return str(e)

class UserViewSet(viewsets.ReadOnlyModelViewSet):

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser:
            return self.queryset
        else:
            return self.queryset.filter(pk=user.pk)

    def get_object(self):
        username = self.kwargs.get('username', None)
        if username:
            qs = self.get_queryset()
            obj = generics.get_object_or_404(qs, username=username)
        else:
            obj = self.request.user
        return obj

    @action(detail=True, methods=["post"], url_path="set_email")
    def set_email(self, request, pk=None):
        user = self.get_object()
        email = request.data.get("email")
        requesting_user = request.user

        if user != requesting_user:
            return Response(
                {"detail": "Not allowed to set email for this user."},
                status=status.HTTP_403_FORBIDDEN
            )

        if not email:
            return Response(
                {"detail": "Email address is required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if user.email:
            return Response(
                {"detail": "User already has an email set."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if settings.ACCOUNT_UNIQUE_EMAIL and EmailAddress.objects.filter(email=email):
            return Response(
                {"detail": "The email address is already in use."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Update the existing EmailAddress
        email_address = EmailAddress.objects.filter(user=user)
        if email_address:
            email_address.update(email=email)

        # Update the User
        user.email = email
        user.save()

        return Response(
            {"detail": "Email set successfully."},
            status=status.HTTP_200_OK
        )

    permission_classes = [permissions.IsAuthenticated]
    queryset = get_user_model().objects.all()
    serializer_class = UserSerializer

register_view(UserViewSet, 'user')
