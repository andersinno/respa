from django.conf import settings
from rest_framework import permissions
from rest_framework.viewsets import ReadOnlyModelViewSet

from resources.api.base import TranslatedModelSerializer
from respa_instructions.models import RespaInstruction

LANGUAGES = [x[0] for x in settings.LANGUAGES]
IMG_UPLOAD_FOLDER = "/media/uploads/"

all_views = []


def register_view(klass, name, base_name=None):
    entry = {"class": klass, "name": name}
    if base_name is not None:
        entry["base_name"] = base_name
    all_views.append(entry)


class RespaInstructionSerializer(TranslatedModelSerializer):
    class Meta:
        model = RespaInstruction
        fields = ("id", "applicable_for", "content")

    def to_representation(self, obj):
        ret = super().to_representation(obj)
        if obj is None:
            return ret

        instruction_content = ret["content"]
        for lang in LANGUAGES:
            lang_specific_content = instruction_content.get(lang)
            if (
                lang_specific_content
                and f'src="{IMG_UPLOAD_FOLDER}' in lang_specific_content
            ):
                lang_specific_content = self._get_content_with_correct_image_link(
                    lang_specific_content
                )
                instruction_content[lang] = lang_specific_content
        return ret

    def _get_content_with_correct_image_link(self, content):
        request = self.context["request"]
        media_url = request.build_absolute_uri(f"{IMG_UPLOAD_FOLDER}")
        content_with_correct_domain = content.replace(
            IMG_UPLOAD_FOLDER,
            media_url,
        )
        return content_with_correct_domain


class RespaUserInstructionView(ReadOnlyModelViewSet):
    serializer_class = RespaInstructionSerializer
    queryset = RespaInstruction.objects.filter(active=True, applicable_for="user")


register_view(
    RespaUserInstructionView, "user_instructions", base_name="user_instructions"
)


class RespaAdminInstructionView(ReadOnlyModelViewSet):
    permission_classes = (permissions.IsAdminUser,)
    serializer_class = RespaInstructionSerializer
    queryset = RespaInstruction.objects.filter(active=True, applicable_for="admin")


register_view(
    RespaAdminInstructionView, "admin_instructions", base_name="admin_instructions"
)
