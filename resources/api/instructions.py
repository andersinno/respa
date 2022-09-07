from django.conf import settings
from rest_framework.viewsets import ReadOnlyModelViewSet

from respa_instructions.models import RespaInstruction
from .base import TranslatedModelSerializer, register_view


LANGUAGES = [x[0] for x in settings.LANGUAGES]
IMG_UPLOAD_FOLDER = '/media/uploads/'


class RespaInstructionSerializer(TranslatedModelSerializer):
    class Meta:
        model = RespaInstruction
        fields = ('id', 'applicable_for', 'content')

    def to_representation(self, obj):
        ret = super().to_representation(obj)
        if obj is None:
            return ret

        instruction_content = ret['content']
        for lang in LANGUAGES:
            lang_specific_content = instruction_content.get(lang)
            if (
                lang_specific_content and
                f'src="{IMG_UPLOAD_FOLDER}' in lang_specific_content
            ):
                lang_specific_content = self._get_content_with_correct_image_link(lang_specific_content)
                instruction_content[lang] = lang_specific_content
        return ret

    def _get_content_with_correct_image_link(self, content):
        request = self.context['request']
        media_url = request.build_absolute_uri(f'{IMG_UPLOAD_FOLDER}')
        content_with_correct_domain = content.replace(
            IMG_UPLOAD_FOLDER,
            media_url,
        )
        return content_with_correct_domain


class RespaInstructionView(ReadOnlyModelViewSet):
    serializer_class = RespaInstructionSerializer
    queryset = RespaInstruction.objects.filter(active=True, applicable_for='applicant')

    def filter_queryset(self, queryset):
        if self.request.user.is_staff:
            queryset = RespaInstruction.objects.filter(active=True)
        return queryset


register_view(RespaInstructionView, 'instructions')
