from django.contrib import admin
from .models import Post, Category, Tag, Comment

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)} # slug 字段会根据 name 自动填充

@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}

class CommentInline(admin.TabularInline):
    model = Comment
    extra = 1 # 默认额外显示一个空的评论表单
    readonly_fields = ('author', 'created_at', 'updated_at')

@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ('title', 'author', 'status', 'category', 'published_at', 'is_featured')
    list_filter = ('status', 'is_featured', 'category', 'tags')
    search_fields = ('title', 'content', 'author__username')
    readonly_fields = ('word_count', 'read_time', 'view_count', 'like_count', 'comment_count', 'created_at', 'updated_at')
    fieldsets = (
        (None, {
            'fields': ('title', 'author', 'content', 'cover_image', 'excerpt')
        }),
        ('组织与状态', {
            'fields': ('status', 'category', 'tags', 'is_featured', 'published_at')
        }),
        ('统计数据 (只读)', {
            'fields': ('view_count', 'like_count', 'comment_count', 'word_count', 'read_time'),
            'classes': ('collapse',) # 默认折叠
        }),
    )
    inlines = [CommentInline] # 在文章详情页内联显示评论

@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ('author', 'post', 'parent', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('content', 'author__username', 'post__title')
    readonly_fields = ('created_at', 'updated_at')