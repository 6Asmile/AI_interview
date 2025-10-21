from django.contrib import admin
from .models import ResumeTemplate
from .services import parse_docx_to_json


@admin.register(ResumeTemplate)
class ResumeTemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'is_public', 'order', 'updated_at')
    list_editable = ('is_public', 'order')
    search_fields = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}

    fieldsets = (
        (None, {
            'fields': ('name', 'slug', 'is_public', 'order')
        }),
        ('模板文件', {
            'fields': ('preview_image', 'source_file', 'description')
        }),
        ('系统生成 (只读)', {
            'classes': ('collapse',),
            'fields': ('structure_json',),
        }),
    )
    readonly_fields = ('structure_json',)

    def save_model(self, request, obj: ResumeTemplate, form, change):
        # 先调用父类的 save_model 保存对象，这样文件才会被写入磁盘
        super().save_model(request, obj, form, change)

        # 检查 source_file 是否存在且有更新
        if obj.source_file and 'source_file' in form.changed_data:
            try:
                # obj.source_file.path 包含了文件的完整服务器路径
                parsed_json = parse_docx_to_json(obj.source_file.path)

                # 将解析得到的 JSON 更新到 structure_json 字段
                obj.structure_json = parsed_json

                # 再次保存模型，但不触发无限循环
                # 我们只更新 structure_json，所以不需要再次调用整个 save_model
                obj.save(update_fields=['structure_json'])

                self.message_user(request, "Word 模板文件已成功解析并更新了 JSON 结构。")
            except Exception as e:
                self.message_user(request, f"解析 Word 文件时出错: {e}", level='ERROR')