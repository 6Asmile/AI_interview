from django.contrib import admin

from .models import (
    Education,
    ProjectExperience,
    Resume,
    ResumeImportJob,
    ResumeSuggestion,
    ResumeVariant,
    ResumeVersion,
    Skill,
    WorkExperience,
)


class EducationInline(admin.TabularInline):
    model = Education
    extra = 0


class WorkExperienceInline(admin.TabularInline):
    model = WorkExperience
    extra = 0


class ProjectExperienceInline(admin.TabularInline):
    model = ProjectExperience
    extra = 0


class SkillInline(admin.TabularInline):
    model = Skill
    extra = 0


@admin.register(Resume)
class ResumeAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'status', 'current_version', 'is_default', 'updated_at')
    list_filter = ('status', 'is_default')
    search_fields = ('title', 'user__username', 'user__email')
    readonly_fields = ('created_at', 'updated_at', 'canonical_schema_version')
    inlines = [EducationInline, WorkExperienceInline, ProjectExperienceInline, SkillInline]


@admin.register(ResumeVersion)
class ResumeVersionAdmin(admin.ModelAdmin):
    list_display = ('resume', 'version_number', 'source', 'schema_version', 'created_by', 'created_at')
    list_filter = ('source', 'schema_version')
    search_fields = ('resume__title', 'resume__user__email', 'change_summary')
    readonly_fields = [field.name for field in ResumeVersion._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(ResumeImportJob)
class ResumeImportJobAdmin(admin.ModelAdmin):
    list_display = ('resume', 'user', 'status', 'parser_name', 'created_at', 'completed_at')
    list_filter = ('status', 'parser_name')
    search_fields = ('resume__title', 'user__email', 'error_message')
    readonly_fields = ('started_at', 'completed_at', 'created_at', 'updated_at')


@admin.register(ResumeSuggestion)
class ResumeSuggestionAdmin(admin.ModelAdmin):
    list_display = ('summary', 'resume', 'base_version', 'status', 'created_by', 'created_at')
    list_filter = ('status',)
    search_fields = ('summary', 'resume__title', 'resume__user__email')


admin.site.register(ResumeVariant)
admin.site.register(Education)
admin.site.register(WorkExperience)
admin.site.register(ProjectExperience)
admin.site.register(Skill)
