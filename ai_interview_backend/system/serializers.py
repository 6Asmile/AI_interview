# system/serializers.py
from rest_framework import serializers
from .models import AISetting

class AISettingSerializer(serializers.ModelSerializer):
    class Meta:
        model = AISetting
        fields = ['ai_model', 'api_key']
        # 将 user 字段排除，因为它总是当前登录用户