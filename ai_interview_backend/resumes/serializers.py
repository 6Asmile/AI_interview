# resumes/serializers.py
from rest_framework import serializers
from .models import Resume, Education, WorkExperience, ProjectExperience, Skill


class ResumeCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Resume
        fields = ['title', 'status']

# --- 子模型序列化器 ---
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
    # 【核心修正】让 end_date 可以为 null
    end_date = serializers.DateField(required=False, allow_null=True)
    class Meta:
        model = WorkExperience
        fields = ['id', 'company', 'position', 'start_date', 'end_date', 'description']

class ProjectExperienceSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)
    # 【核心修正】让 end_date 可以为 null
    end_date = serializers.DateField(required=False, allow_null=True)
    class Meta:
        model = ProjectExperience
        fields = ['id', 'project_name', 'role', 'start_date', 'end_date', 'description']


# --- 支持深度嵌套更新的主序列化器 ---
class ResumeDetailSerializer(serializers.ModelSerializer):
    skills = SkillSerializer(many=True, required=False) # 【修正】设为非必需
    educations = EducationSerializer(many=True, required=False)
    work_experiences = WorkExperienceSerializer(many=True, required=False)
    project_experiences = ProjectExperienceSerializer(many=True, required=False)

    class Meta:
        model = Resume
        # 【核心修正】在 fields 中添加 file_url
        fields = [
            'id', 'title', 'full_name', 'phone', 'email', 'job_title',
            'city', 'summary', 'status', 'parsed_content', 'file_url',
            'skills', 'educations', 'work_experiences', 'project_experiences'
        ]

    def update(self, instance, validated_data):
        # 【终极核心修正】确保 project_experiences 和 skills 被正确处理
        nested_fields = {
            'skills': (Skill, validated_data.pop('skills', None)),
            'educations': (Education, validated_data.pop('educations', None)),
            'work_experiences': (WorkExperience, validated_data.pop('work_experiences', None)),
            'project_experiences': (ProjectExperience, validated_data.pop('project_experiences', None))
        }

        # 更新主 Resume 实例的字段
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        # 处理嵌套字段
        for field_name, (model_class, data_list) in nested_fields.items():
            # 如果前端没有传递这个字段 (例如只更新了个人信息)，则 data_list 会是 None，此时我们跳过处理
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