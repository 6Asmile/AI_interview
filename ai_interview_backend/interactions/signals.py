from django.db.models import F
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import Like, Bookmark, Follow
from notifications.models import Notification
from blog.models import Comment, Post


# --- Like Signals ---
@receiver(post_save, sender=Like)
def create_like_notification_and_update_count(sender, instance, created, **kwargs):
    """
    监听到新的点赞创建时：
    1. 增加文章的点赞数。
    2. 为文章作者创建一条通知。
    """
    if created:
        # 使用 F() 对象原子性地增加计数值，避免竞态条件
        Post.objects.filter(id=instance.post.id).update(like_count=F('like_count') + 1)

        # 只有在文章作者不是点赞者本人时才发送通知
        if instance.post.author != instance.user:
            Notification.objects.create(
                recipient=instance.post.author,
                actor=instance.user,
                verb=Notification.VerbChoices.LIKED_POST,
                target=instance.post
            )


@receiver(post_delete, sender=Like)
def update_like_count_on_delete(sender, instance, **kwargs):
    """
    监听到点赞被删除时（即取消点赞），减少文章的点赞数。
    """
    Post.objects.filter(id=instance.post.id).update(like_count=F('like_count') - 1)


# --- Bookmark Signals ---
@receiver(post_save, sender=Bookmark)
def create_bookmark_notification_and_update_count(sender, instance, created, **kwargs):
    """
    监听到新的收藏创建时：
    1. 增加文章的收藏数。
    2. 为文章作者创建一条通知。
    """
    if created:
        Post.objects.filter(id=instance.post.id).update(bookmark_count=F('bookmark_count') + 1)

        if instance.post.author != instance.user:
            Notification.objects.create(
                recipient=instance.post.author,
                actor=instance.user,
                verb=Notification.VerbChoices.BOOKMARKED_POST,
                target=instance.post
            )


@receiver(post_delete, sender=Bookmark)
def update_bookmark_count_on_delete(sender, instance, **kwargs):
    """
    监听到收藏被删除时，减少文章的收藏数。
    """
    Post.objects.filter(id=instance.post.id).update(bookmark_count=F('bookmark_count') - 1)


# --- Follow Signals ---
@receiver(post_save, sender=Follow)
def create_follow_notification(sender, instance, created, **kwargs):
    """
    监听到新的关注创建时，为被关注者创建一条通知。
    （关注数通常在 User 模型中通过 @property 计算，或另建计数模型，此处暂不处理）
    """
    if created and instance.followed != instance.follower:
        Notification.objects.create(
            recipient=instance.followed,
            actor=instance.follower,
            verb=Notification.VerbChoices.FOLLOWED
        )


# --- Comment Signals ---
@receiver(post_save, sender=Comment)
def create_comment_notification_and_update_count(sender, instance, created, **kwargs):
    """
    监听到新的评论/回复创建时：
    1. 增加文章的评论总数。
    2. 根据场景（评论或回复）为相关用户创建通知。
    """
    if created:
        # 1. 统一增加文章的评论总数
        Post.objects.filter(id=instance.post.id).update(comment_count=F('comment_count') + 1)

        # 2. 根据不同场景发送通知
        # 场景A: 直接评论文章
        if instance.parent is None:
            if instance.post.author != instance.author:
                Notification.objects.create(
                    recipient=instance.post.author,
                    actor=instance.author,
                    verb=Notification.VerbChoices.COMMENTED,
                    target=instance.post,
                    action_object=instance
                )
        # 场景B: 回复别人的评论
        else:
            # 确保不给自己发通知
            if instance.parent.author != instance.author:
                Notification.objects.create(
                    recipient=instance.parent.author,
                    actor=instance.author,
                    verb=Notification.VerbChoices.REPLIED,
                    target=instance.parent,  # target 是被回复的评论
                    action_object=instance  # action_object 是这条新回复
                )


@receiver(post_delete, sender=Comment)
def update_comment_count_on_delete(sender, instance, **kwargs):
    """
    监听到评论被删除时，减少文章的评论总数。
    """
    Post.objects.filter(id=instance.post.id).update(comment_count=F('comment_count') - 1)