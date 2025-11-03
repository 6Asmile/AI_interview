from rest_framework import serializers
from .models import Like, Bookmark, Follow

class FollowSerializer(serializers.ModelSerializer):
    class Meta:
        model = Follow
        fields = ('followed',) # 创建时只需要提供被关注者的ID