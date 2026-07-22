from rest_framework.permissions import BasePermission

from .models import StaffAccount


class StaffPermission(BasePermission):
    def has_permission(self, request, view):
        account = request.user
        if not isinstance(account, StaffAccount) or not account.is_authenticated or not account.is_active:
            return False
        required = set(getattr(view, 'required_permissions', []))
        permissions = account.permission_set()
        return '*' in permissions or not required or required.issubset(permissions)
