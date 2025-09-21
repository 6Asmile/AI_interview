# users/views.py
from rest_framework import generics, permissions
from .models import User
from .serializers import UserRegisterSerializer

