# resumes/serializers.py
from rest_framework import serializers
from .models import Resume, Education, WorkExperience, ProjectExperience, Skill


# --- 子模型序列化器 (保持不变，确保它们存在) ---
class SkillSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)

    class Meta:
        model = Skill
        fields = ['id', 'skill_name', 'proficiency']


class EducationSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)

    class Meta:
        model = Education
        fields = ['id', 'school', 'degree', 'major', 'start_date', 'end_date']


class WorkExperienceSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)
    end_date = serializers.DateField(required=False, allow_null=True)

    class Meta:
        model = WorkExperience
        fields = ['id', 'company', 'position', 'start_date', 'end_date', 'description']


class ProjectExperienceSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)
    end_date = serializers.DateField(required=False, allow_null=True)

    class Meta:
        model = ProjectExperience
        fields = ['id', 'project_name', 'role', 'start_date', 'end_date', 'description']


# --- 用于在线创建的简单序列化器 ---
# --- 【核心修复】升级创建简历的序列化器 ---
class ResumeCreateSerializer(serializers.ModelSerializer):
    # 允许在创建时直接传入 content_json 和 template_name
    # read_only=False (默认) 意味着这些字段是可写的
    # required=False 意味着它们是可选的
    content_json = serializers.JSONField(required=False, allow_null=True)
    template_name = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = Resume
        # 将新字段添加到 fields 列表中
        fields = ['title', 'status', 'content_json', 'template_name']


# --- 【核心修复】支持深度嵌套读写的主序列化器 ---
class ResumeDetailSerializer(serializers.ModelSerializer):
    # 【修复#1】为所有嵌套/关联字段恢复或添加正确的序列化器定义
    skills = SkillSerializer(many=True, required=False)
    educations = EducationSerializer(many=True, required=False)
    work_experiences = WorkExperienceSerializer(many=True, required=False)
    project_experiences = ProjectExperienceSerializer(many=True, required=False)

    class Meta:
        model = Resume
        # 【修复#2】确保 fields 列表中的所有字段都在模型中定义，或者在序列化器中显式定义
        fields = [
            'id', 'title', 'status', 'parsed_content', 'file_url',
            'template_name',  # <-- 【核心新增】
            'content_json',  # 新增的JSON字段

            # 模型中存在的、需要被序列化的简单字段
            'full_name', 'phone', 'email', 'job_title',
            'city', 'summary',

            # 在上面显式定义的嵌套字段
            'skills', 'educations', 'work_experiences', 'project_experiences'
        ]
        read_only_fields = ('file_url',)  # file_url 是只读属性

    def update(self, instance, validated_data):
        # 【提醒】这个复杂的 update 方法是为了兼容旧的结构化数据编辑，暂时保留。
        # 如果只使用新的 JSON 编辑器，这个方法可以被简化或移除。
        nested_fields = {
            'skills': (Skill, validated_data.pop('skills', None)),
            'educations': (Education, validated_data.pop('educations', None)),
            'work_experiences': (WorkExperience, validated_data.pop('work_experiences', None)),
            'project_experiences': (ProjectExperience, validated_data.pop('project_experiences', None))
        }

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        for field_name, (model_class, data_list) in nested_fields.items():
            if data_list is None:
                continue

            current_ids = []
            for item_data in data_list:
                item_id = item_data.get('id')
                if item_id:
                    model_class.objects.filter(id=item_id, resume=instance).update(**item_data)
                    current_ids.append(item_id)
                else:
                    new_item = model_class.objects.create(resume=instance, **item_data)
                    current_ids.append(new_item.id)

            getattr(instance, field_name).exclude(id__in=current_ids).delete()

        return instance