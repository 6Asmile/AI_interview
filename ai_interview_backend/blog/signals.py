# ai-interview-backend/blog/signals.py (新建文件)

from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Post
from .tasks import generate_recommendations_for_post

@receiver(post_save, sender=Post)
def trigger_recommendation_generation(sender, instance, created, **kwargs):
    """
    当文章被创建或更新时，异步触发推荐生成任务。
    """
    # 只为已发布的文章生成推荐
    if instance.status == 'published':
        print(f"Post '{instance.title}' saved, triggering recommendation task.")
        # 使用 .delay() 来异步执行任务
        generate_recommendations_for_post.delay(instance.id)