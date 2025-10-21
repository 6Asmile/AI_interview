from rest_framework import serializers
from .models import ResumeTemplate

class ResumeTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ResumeTemplate
        # 只暴露前端需要的字段
        fields = ('id', 'name', 'slug', 'preview_image', 'structure_json', 'description')