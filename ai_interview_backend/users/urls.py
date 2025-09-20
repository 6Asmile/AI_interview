# users/urls.py
from django.urls import path
from .views import UserRegisterView

urlpatterns = [
    path('register/', UserRegisterView.as_view(), name='user-register'),
]