# ai_interview_backend/reports/models.py

from django.db import models
from users.models import User
from resumes.models import Resume
import uuid


class ResumeAnalysisReport(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='analysis_reports')
    resume = models.ForeignKey(Resume, on_delete=models.CASCADE, related_name='analysis_reports')
    resume_version = models.ForeignKey(
        'resumes.ResumeVersion', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='analysis_reports', verbose_name='简历版本快照来源'
    )
    job_target = models.ForeignKey(
        'careers.JobTarget', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='resume_analysis_reports', verbose_name='目标岗位来源'
    )
    resume_snapshot = models.JSONField(default=dict, blank=True, verbose_name='简历版本快照')
    model_config_snapshot = models.JSONField(default=dict, blank=True, verbose_name='模型配置快照')
    evidence_sources = models.JSONField(default=list, blank=True, verbose_name='证据来源')

    # 存储原始的 JD 文本，以便追溯
    jd_text = models.TextField(verbose_name='目标岗位JD')

    # 存储AI返回的完整JSON报告
    report_data = models.JSONField(verbose_name='AI分析报告JSON')

    # 冗余一些关键字段，方便在列表页快速展示和筛选
    overall_score = models.IntegerField(default=0, verbose_name='综合匹配度得分')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = '简历分析报告'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.resume.title} 的分析报告 ({self.created_at.strftime('%Y-%m-%d')})"
