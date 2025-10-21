from rest_framework import generics, permissions
from .models import ResumeTemplate
from .serializers import ResumeTemplateSerializer

class ResumeTemplateListView(generics.ListAPIView):
    """
    获取所有已发布的简历模板列表。
    """
    queryset = ResumeTemplate.objects.filter(is_public=True).order_by('order')
    serializer_class = ResumeTemplateSerializer
    permission_classes = [permissions.AllowAny] # 允许任何人访问