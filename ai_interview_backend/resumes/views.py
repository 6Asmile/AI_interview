from rest_framework import viewsets, permissions
from .models import Resume, Education, WorkExperience, ProjectExperience, Skill
from .serializers import (
    ResumeSerializer,
    EducationSerializer,
    WorkExperienceSerializer,
    ProjectExperienceSerializer,
    SkillSerializer
)
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status

# 这是一个基础 ViewSet，用于处理所有子模型
class BaseResumeDetailViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # 确保用户只能操作自己简历下的条目
        resume_id = self.kwargs.get('resume_pk')
        return self.queryset.filter(resume__user=self.request.user, resume_id=resume_id)

    def perform_create(self, serializer):
        # 创建时，自动关联到对应的简历
        resume_id = self.kwargs.get('resume_pk')
        resume = Resume.objects.get(id=resume_id, user=self.request.user)
        serializer.save(resume=resume)

# --- 为每个模型创建具体的 ViewSet ---

class EducationViewSet(BaseResumeDetailViewSet):
    queryset = Education.objects.all()
    serializer_class = EducationSerializer

class WorkExperienceViewSet(BaseResumeDetailViewSet):
    queryset = WorkExperience.objects.all()
    serializer_class = WorkExperienceSerializer

class ProjectExperienceViewSet(BaseResumeDetailViewSet):
    queryset = ProjectExperience.objects.all()
    serializer_class = ProjectExperienceSerializer

class SkillViewSet(BaseResumeDetailViewSet):
    queryset = Skill.objects.all()
    serializer_class = SkillSerializer


# --- 主 Resume ViewSet ---
class ResumeViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ResumeSerializer

    def get_queryset(self):
        # 用户只能看到和操作自己的简历
        return Resume.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        # 创建简历时，自动关联当前用户
        serializer.save(user=self.request.user)