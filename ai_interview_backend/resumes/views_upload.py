# ai_interview_backend/resumes/views_upload.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.core.files.storage import FileSystemStorage
import os
import uuid


class FileUploadView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        file_obj = request.FILES.get('file')
        # 新增：从URL或请求参数获取上传目录，默认为'uploads'
        upload_dir = request.data.get('dir', 'uploads')

        if not file_obj:
            return Response({'error': '没有提供文件'}, status=status.HTTP_400_BAD_REQUEST)

        # 可以在这里添加更严格的文件类型和大小校验
        # ...

        ext = os.path.splitext(file_obj.name)[1].lower()
        unique_filename = f"{uuid.uuid4()}{ext}"

        # 使用动态的存储路径
        save_path = os.path.join(upload_dir, unique_filename)

        fs = FileSystemStorage()
        filename = fs.save(save_path, file_obj)
        file_url = fs.url(filename)

        return Response({
            'message': '文件上传成功',
            'file_url': file_url  # 返回的是相对URL, e.g., /media/avatars/xxxx.jpg
        }, status=status.HTTP_201_CREATED)