from rest_framework import serializers
from .models import Resume, Education, WorkExperience, ProjectExperience, Skill

# --- 子模型序列化器 ---

class EducationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Education
        exclude = ['resume'] # 在嵌套时，不需要重复返回 resume ID

class WorkExperienceSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkExperience
        exclude = ['resume']

class ProjectExperienceSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectExperience
        exclude = ['resume']

class SkillSerializer(serializers.ModelSerializer):
    class Meta:
        model = Skill
        exclude = ['resume']


# --- 主 Resume 序列化器 ---

class ResumeSerializer(serializers.ModelSerializer):
    """
    用于展示完整的、包含所有详情的简历。
    """
    # 使用嵌套序列化器，并指定为只读
    educations = EducationSerializer(many=True, read_only=True)
    work_experiences = WorkExperienceSerializer(many=True, read_only=True)
    project_experiences = ProjectExperienceSerializer(many=True, read_only=True)
    skills = SkillSerializer(many=True, read_only=True)

    class Meta:
        model = Resume
        # 包含所有 Resume 模型自身的字段，以及我们上面定义的嵌套字段
        fields = [
            'id', 'user', 'title', 'full_name', 'phone', 'email', 
            'job_title', 'city', 'summary', 'is_default', 'status',
            'created_at', 'updated_at',
            # 嵌套的详情
            'educations', 'work_experiences', 'project_experiences', 'skills',
            # 文件相关字段
            'file', 'parsed_content', 
        ]
        read_only_fields = ['user']