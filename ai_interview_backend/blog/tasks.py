# ai-interview-backend/blog/tasks.py
from celery import shared_task
from django.utils import timezone
from .models import Post, DailyPostStats


@shared_task
def record_daily_stats():
    today = timezone.now().date()
    posts = Post.objects.all()

    for post in posts:
        # 使用 update_or_create 来避免重复创建
        DailyPostStats.objects.update_or_create(
            post=post,
            date=today,
            defaults={
                'views': post.view_count,
                'likes': post.like_count
            }
        )
    return f"Successfully recorded daily stats for {posts.count()} posts on {today}."