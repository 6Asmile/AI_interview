# resumes/views.py
from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from .models import Resume, Education, WorkExperience, ProjectExperience, Skill
from .serializers import (
    ResumeDetailSerializer,
    EducationSerializer,
    WorkExperienceSerializer,
    ProjectExperienceSerializer,
    SkillSerializer,
    ResumeCreateSerializer
)
# 【新增】导入简历解析服务
from .services import extract_text_from_file

class ResumeViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Resume.objects.filter(user=self.request.user).order_by('-updated_at')

    def get_serializer_class(self):
        if self.action == 'create':
            # 在 create 方法中，我们会处理文件上传，所以这里依然可以使用简单的序列化器
            # 也可以不在这里指定，在 create 方法中直接处理
            return ResumeCreateSerializer
        return ResumeDetailSerializer

    def create(self, request, *args, **kwargs):
        """
        【核心修改】重写 create 方法以支持文件上传和在线创建两种模式
        """
        # --- 模式一：文件上传 ---
        if 'file' in request.FILES:
            file_obj = request.FILES['file']
            title = request.data.get('title', file_obj.name) # 如果没提供标题，用文件名

            # 创建一个初始的 Resume 实例并保存文件
            resume_instance = Resume(user=request.user, title=title, file=file_obj)
            resume_instance.save() # 这里会触发文件保存到 media/resumes/

            try:
                # 文件保存后，它的路径是 resume_instance.file.path
                # 调用服务从保存的文件中提取文本
                extracted_text = extract_text_from_file(resume_instance.file.path)

                if extracted_text:
                    resume_instance.parsed_content = extracted_text
                    resume_instance.status = Resume.Status.PARSED # 标记为“已解析”
                    resume_instance.save()
                else:
                    resume_instance.status = Resume.Status.FAILED # 标记为“解析失败”
                    resume_instance.save()
            except Exception as e:
                print(f"解析简历文件失败: {e}")
                resume_instance.status = Resume.Status.FAILED
                resume_instance.save()

            # 使用 Detail 序列化器返回完整的对象
            output_serializer = ResumeDetailSerializer(resume_instance)
            return Response(output_serializer.data, status=status.HTTP_201_CREATED)

        # --- 模式二：在线创建 ---
        else:
            serializer = ResumeCreateSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            # perform_create 会调用 serializer.save() 并注入 user
            self.perform_create(serializer)
            # 使用 Detail 序列化器返回完整的对象
            output_serializer = ResumeDetailSerializer(serializer.instance)
            headers = self.get_success_headers(output_serializer.data)
            return Response(output_serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def perform_create(self, serializer):
        # 创建简历时，自动关联当前用户
        serializer.save(user=self.request.user)


# --- 子模型的 ViewSet (保持不变) ---

class BaseResumeDetailViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        resume_pk = self.kwargs.get('resume_pk')
        if resume_pk:
            return self.queryset.filter(resume__user=self.request.user, resume_id=resume_pk)
        return self.queryset.none()

    def perform_create(self, serializer):
        resume_pk = self.kwargs.get('resume_pk')
        try:
            resume = Resume.objects.get(id=resume_pk, user=self.request.user)
            serializer.save(resume=resume)
        except Resume.DoesNotExist:
            pass

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