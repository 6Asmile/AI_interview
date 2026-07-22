import os
import uuid

from django.core.files.storage import FileSystemStorage
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from core.throttles import UploadRateThrottle
from core.uploads import validate_uploaded_file


class FileUploadView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [UploadRateThrottle]
    allowed_directories = {'uploads', 'avatars', 'resume-assets'}
    allowed_extensions = {'.png', '.jpg', '.jpeg', '.webp', '.pdf'}

    def post(self, request, *args, **kwargs):
        file_obj = request.FILES.get('file')
        if not file_obj:
            return Response({'code': 'file_required', 'message': '没有提供文件。'}, status=status.HTTP_400_BAD_REQUEST)
        upload_dir = str(request.data.get('dir') or 'uploads').strip().lower()
        if upload_dir not in self.allowed_directories:
            return Response({'code': 'invalid_upload_directory', 'message': '上传目录无效。'}, status=status.HTTP_400_BAD_REQUEST)
        extension = validate_uploaded_file(
            file_obj,
            allowed_extensions=self.allowed_extensions,
            max_bytes=10 * 1024 * 1024,
            max_pdf_pages=100,
        )
        unique_filename = f'{uuid.uuid4()}{extension}'
        save_path = os.path.join(upload_dir, unique_filename)
        storage = FileSystemStorage()
        filename = storage.save(save_path, file_obj)
        return Response({'message': '文件上传成功', 'file_url': storage.url(filename)}, status=status.HTTP_201_CREATED)
