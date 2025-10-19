# ai_interview_backend/reports/serializers.py (新建文件)

from rest_framework import serializers
from .models import ResumeAnalysisReport

class ResumeAnalysisReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = ResumeAnalysisReport
        fields = '__all__'