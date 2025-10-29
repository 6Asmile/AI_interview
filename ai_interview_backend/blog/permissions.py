from rest_framework import permissions

class IsOwnerOrReadOnly(permissions.BasePermission):
    """
    自定义权限，只允许对象的所有者编辑它。
    """
    def has_object_permission(self, request, view, obj):
        # 对于读取权限（GET, HEAD, OPTIONS），总是允许
        if request.method in permissions.SAFE_METHODS:
            return True

        # 写入权限只开放给文章的作者
        return obj.author == request.user