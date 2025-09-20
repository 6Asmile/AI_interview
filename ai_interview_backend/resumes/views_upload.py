# resumes/views_upload.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.core.files.storage import FileSystemStorage
import os
import uuid
from django.conf import settings

class FileUploadView(APIView):
    # 同样需要登录权限才能上传
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        file_obj = request.FILES.get('file')
        if not file_obj:
            return Response({'error': '没有提供文件'}, status=status.HTTP_400_BAD_REQUEST)

        # 为了防止文件名冲突，我们生成一个唯一的文件名
        ext = os.path.splitext(file_obj.name)[1] # 获取文件扩展名，如 .pdf
        unique_filename = f"{uuid.uuid4()}{ext}"

        # 定义存储路径 (在 MEDIA_ROOT 下的 'resumes' 文件夹内)
        save_path = os.path.join('resumes', unique_filename)

        # 使用 FileSystemStorage 来保存文件
        fs = FileSystemStorage()
        filename = fs.save(save_path, file_obj)

        # 获取文件的完整访问 URL
        file_url = fs.url(filename)

        return Response({
            'message': '文件上传成功',
            'file_url': file_url
        }, status=status.HTTP_201_CREATED)