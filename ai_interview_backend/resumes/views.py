# resumes/views.py
import os

from rest_framework import viewsets, permissions, status  # 1. 导入 status
from rest_framework.response import Response  # 2. 导入 Response
from rest_framework.parsers import MultiPartParser, FormParser  # 3. 导入解析器
from .models import Resume
from .serializers import ResumeSerializer
from .services import extract_text_from_file  # 4. 导入我们的解析服务
from .serializers import ResumeSerializer, ResumeCreateSerializer


class ResumeViewSet(viewsets.ModelViewSet):
    queryset = Resume.objects.all()  # 默认 queryset
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def get_queryset(self):
        # 动态 queryset，确保用户只能看到自己的简历
        return Resume.objects.filter(user=self.request.user)

    def get_serializer_class(self):
        # 2. 根据不同的 action，返回不同的序列化器
        if self.action == 'create':
            return ResumeCreateSerializer
        return ResumeSerializer

    def create(self, request, *args, **kwargs):
        file_obj = request.FILES.get('file')
        if not file_obj:
            return Response({'error': '没有提供简历文件'}, status=status.HTTP_400_BAD_REQUEST)

        # 3. 使用 get_serializer() 来获取正确的 CreateSerializer
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # 使用 serializer.validated_data 来获取干净的数据
        title = serializer.validated_data.get('title') or file_obj.name.replace(os.path.splitext(file_obj.name)[1], "")

        # --- 文件保存和解析逻辑保持不变 ---

        # 创建实例，但先不保存
        resume_instance = Resume(user=request.user, title=title)

        # 关联文件并保存，Django 会处理上传
        resume_instance.file = file_obj
        resume_instance.save()

        # 更新其他元数据
        resume_instance.file_type = os.path.splitext(file_obj.name)[1].lower().replace('.', '')
        resume_instance.file_size = round(file_obj.size / 1024)

        # 解析文本
        try:
            parsed_text = extract_text_from_file(resume_instance.file.path)
            resume_instance.parsed_content = parsed_text
            resume_instance.status = Resume.Status.PARSED if parsed_text else Resume.Status.FAILED
        except Exception as e:
            print(f"解析文件失败: {e}")
            resume_instance.status = Resume.Status.FAILED

        # 最终保存所有更新
        resume_instance.save()

        # 4. 使用 ResumeSerializer (用于输出) 来返回完整数据
        output_serializer = ResumeSerializer(resume_instance)
        headers = self.get_success_headers(output_serializer.data)
        return Response(output_serializer.data, status=status.HTTP_201_CREATED, headers=headers)