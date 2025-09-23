from django.contrib import admin
from .models import Resume, Education, WorkExperience, ProjectExperience, Skill


# 使用 TabularInline，让我们可以在简历详情页直接编辑关联的经历
class EducationInline(admin.TabularInline):
    model = Education
    extra = 1  # 默认显示一个空的教育经历表单


class WorkExperienceInline(admin.TabularInline):
    model = WorkExperience
    extra = 1


class ProjectExperienceInline(admin.TabularInline):
    model = ProjectExperience
    extra = 1


class SkillInline(admin.TabularInline):
    model = Skill
    extra = 1


@admin.register(Resume)
class ResumeAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'status', 'is_default', 'updated_at')
    list_filter = ('status', 'is_default', 'user')
    search_fields = ('title', 'user__username', 'user__email')
    readonly_fields = ('created_at', 'updated_at')

    # 将所有子模型以内联的方式添加到简历管理页面
    inlines = [
        EducationInline,
        WorkExperienceInline,
        ProjectExperienceInline,
        SkillInline,
    ]


# 我们也可以单独注册这些模型，以便独立管理
@admin.register(Education)
class EducationAdmin(admin.ModelAdmin):
    list_display = ('school', 'degree', 'major', 'resume')
    search_fields = ('school', 'major')


@admin.register(WorkExperience)
class WorkExperienceAdmin(admin.ModelAdmin):
    list_display = ('company', 'position', 'resume')
    search_fields = ('company', 'position')


@admin.register(ProjectExperience)
class ProjectExperienceAdmin(admin.ModelAdmin):
    list_display = ('project_name', 'role', 'resume')
    search_fields = ('project_name', 'role')


@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    list_display = ('skill_name', 'proficiency', 'resume')
    search_fields = ('skill_name',)