from django.db import models
from django.conf import settings
from django.contrib.contenttypes.fields import GenericRelation


class Category(models.Model):
    name = models.CharField(max_length=50, unique=True, verbose_name="分类名称")
    slug = models.SlugField(unique=True, help_text="用于URL的唯一标识, 建议使用英文或拼音")
    description = models.TextField(blank=True, verbose_name="分类描述")
    # 【核心新增】添加默认排序
    ordering = ['name']
    class Meta:
        verbose_name = "文章分类"
        verbose_name_plural = verbose_name

    def __str__(self):
        return self.name


class Tag(models.Model):
    name = models.CharField(max_length=50, unique=True, verbose_name="标签名称")
    slug = models.SlugField(unique=True, help_text="用于URL的唯一标识, 建议使用英文或拼音")
    # 【核心新增】添加默认排序
    ordering = ['name']
    class Meta:
        verbose_name = "文章标签"
        verbose_name_plural = verbose_name

    def __str__(self):
        return self.name


class Post(models.Model):
    class PostStatus(models.TextChoices):
        DRAFT = 'draft', '草稿'
        PENDING = 'pending', '待审核'
        PUBLISHED = 'published', '已发布'
        PRIVATE = 'private', '仅自己可见'

    title = models.CharField(max_length=200, verbose_name="文章标题")
    content = models.TextField(verbose_name="文章内容 (Markdown)")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="posts",
                               verbose_name="作者")

    status = models.CharField(max_length=10, choices=PostStatus.choices, default=PostStatus.DRAFT,
                              verbose_name="文章状态", db_index=True)

    cover_image = models.ImageField(upload_to="post_covers/", blank=True, null=True, verbose_name="封面图")
    excerpt = models.CharField(max_length=255, blank=True, verbose_name="文章摘要")
    word_count = models.IntegerField(default=0, editable=False, verbose_name="字数")
    read_time = models.IntegerField(default=0, editable=False, help_text="预计阅读时间（分钟）")

    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name="posts",
                                 verbose_name="分类")
    tags = models.ManyToManyField(Tag, blank=True, related_name="posts", verbose_name="标签")
    is_featured = models.BooleanField(default=False, verbose_name="是否精选", db_index=True)

    view_count = models.PositiveIntegerField(default=0, editable=False, verbose_name="浏览量")
    like_count = models.PositiveIntegerField(default=0, editable=False, verbose_name="点赞数")
    comment_count = models.PositiveIntegerField(default=0, editable=False, verbose_name="评论数")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    published_at = models.DateTimeField(blank=True, null=True, verbose_name="预定发布时间", db_index=True)

    notifications = GenericRelation('notifications.Notification', related_query_name='post')

    class Meta:
        verbose_name = "文章"
        verbose_name_plural = verbose_name
        ordering = ['-published_at', '-created_at']

    def __str__(self):
        return self.title


class Comment(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="comments", verbose_name="所属文章")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="comments",
                               verbose_name="评论者")
    content = models.TextField(verbose_name="评论内容 (Markdown)")

    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='replies',
                               verbose_name="父评论")

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    notifications = GenericRelation('notifications.Notification', related_query_name='comment')

    class Meta:
        verbose_name = "评论"
        verbose_name_plural = verbose_name
        ordering = ['created_at']

    def __str__(self):
        author_name = getattr(self.author, 'username', '未知用户')
        post_title = getattr(self.post, 'title', '未知文章')
        return f"{author_name} 对《{post_title}》的评论"
