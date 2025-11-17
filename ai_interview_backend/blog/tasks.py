# ai-interview-backend/blog/tasks.py
from celery import shared_task
from django.utils import timezone
from .models import Post, DailyPostStats
from .recommendations import calculate_recommendations
from django.core.cache import cache

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


@shared_task
def generate_recommendations_for_post(post_id: int):
    """
    为单篇文章生成推荐并存入 Redis 缓存。
    """
    try:
        post = Post.objects.get(id=post_id)
        recommended_ids = calculate_recommendations(post)

        # 缓存键的格式：recommendations:post_id
        cache_key = f"recommendations:{post_id}"
        # 缓存有效期设置为 1 天 (86400秒)，之后会自动过期或被下次更新覆盖
        cache.set(cache_key, recommended_ids, timeout=86400)

        return f"Successfully generated recommendations for Post ID {post_id}"
    except Post.DoesNotExist:
        return f"Post with ID {post_id} not found."