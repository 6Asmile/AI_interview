from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.contenttypes.models import ContentType
from .models import Like, Bookmark, Follow
from notifications.models import Notification
from blog.models import Comment # 需要导入 Comment
# from .tasks import send_notification_task # 我们将很快创建这个 Celery task

@receiver(post_save, sender=Like)
def create_like_notification(sender, instance, created, **kwargs):
    """监听到新的点赞创建时，发送通知。"""
    if created:
        # 只有在文章作者不是点赞者本人时才发送通知
        if instance.post.author != instance.user:
            Notification.objects.create(
                recipient=instance.post.author,
                actor=instance.user,
                verb=Notification.VerbChoices.LIKED_POST,
                target=instance.post
            )
            # 异步任务（未来）: send_notification_task.delay(...)

@receiver(post_save, sender=Bookmark)
def create_bookmark_notification(sender, instance, created, **kwargs):
    """监听到新的收藏创建时，发送通知。"""
    if created and instance.post.author != instance.user:
        Notification.objects.create(
            recipient=instance.post.author,
            actor=instance.user,
            verb=Notification.VerbChoices.BOOKMARKED_POST,
            target=instance.post
        )

@receiver(post_save, sender=Follow)
def create_follow_notification(sender, instance, created, **kwargs):
    """监听到新的关注创建时，发送通知。"""
    if created and instance.followed != instance.follower:
        Notification.objects.create(
            recipient=instance.followed,
            actor=instance.follower,
            verb=Notification.VerbChoices.FOLLOWED
        )

# 我们可以把评论相关的信号也放在这里，集中管理
@receiver(post_save, sender=Comment)
def create_comment_notification(sender, instance, created, **kwargs):
    """监听到新的评论/回复创建时，发送通知。"""
    if created:
        # 场景1: 评论了文章
        if instance.parent is None:
            # 评论者不是作者本人
            if instance.post.author != instance.author:
                Notification.objects.create(
                    recipient=instance.post.author,
                    actor=instance.author,
                    verb=Notification.VerbChoices.COMMENTED,
                    target=instance.post,
                    action_object=instance
                )
        # 场景2: 回复了别人的评论
        else:
            # 回复者不是被回复者本人
            if instance.parent.author != instance.author:
                Notification.objects.create(
                    recipient=instance.parent.author,
                    actor=instance.author,
                    verb=Notification.VerbChoices.REPLIED,
                    target=instance.parent, # target 是被回复的评论
                    action_object=instance # action_object 是这条新回复
                )