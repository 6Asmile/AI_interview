# ai-interview-backend/blog/recommendations.py (新建文件)

from django.db.models import Q, Count
from .models import Post

# 定义权重
TAG_MATCH_SCORE = 5
CATEGORY_MATCH_SCORE = 2


def calculate_recommendations(post: Post, top_n: int = 5) -> list[int]:
    """
    为给定的文章计算推荐文章列表。

    :param post: 源文章实例
    :param top_n: 需要推荐的文章数量
    :return: 推荐文章的 ID 列表
    """
    if not post.tags.exists():
        # 如果文章没有标签，则返回近期热门文章作为备选
        # 这里可以根据 view_count, like_count 等排序
        popular_posts = Post.objects.filter(status='published').exclude(id=post.id).order_by('-view_count')[:top_n]
        return [p.id for p in popular_posts]

    # 获取源文章的所有标签 ID
    source_tags = post.tags.values_list('id', flat=True)

    # 查找至少有一个相同标签或相同分类的文章
    candidate_posts = Post.objects.filter(
        Q(tags__in=source_tags) | Q(category=post.category),
        status='published'
    ).exclude(id=post.id).distinct()

    # 计算每篇文章的得分
    scores = {}
    for candidate in candidate_posts:
        score = 0
        # 计算标签匹配得分
        shared_tags_count = candidate.tags.filter(id__in=source_tags).count()
        score += shared_tags_count * TAG_MATCH_SCORE
        # 计算分类匹配得分
        if post.category and candidate.category == post.category:
            score += CATEGORY_MATCH_SCORE

        if score > 0:
            scores[candidate.id] = score

    # 按得分排序，并选出 top_n
    sorted_post_ids = sorted(scores, key=scores.get, reverse=True)

    return sorted_post_ids[:top_n]