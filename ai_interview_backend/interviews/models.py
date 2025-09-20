# interviews/models.py
from django.db import models
import uuid
from users.models import User
from resumes.models import Resume


class InterviewSession(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', '待开始'
        RUNNING = 'running', '进行中'
        FINISHED = 'finished', '已完成'
        CANCELED = 'canceled', '已取消'

    class Difficulty(models.TextChoices):
        EASY = 'easy', '简单'
        MEDIUM = 'medium', '中等'
        HARD = 'hard', '困难'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name='会话 UUID')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='interview_sessions', verbose_name='所属用户')
    resume = models.ForeignKey(Resume, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='关联简历')

    job_position = models.CharField(max_length=100, verbose_name='目标岗位')
    difficulty = models.CharField(max_length=20, choices=Difficulty.choices, default=Difficulty.MEDIUM,
                                  verbose_name='难度')
    question_count = models.IntegerField(default=5, verbose_name='问题数量')

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, verbose_name='状态')
    duration = models.IntegerField(null=True, blank=True, verbose_name='持续时间 (秒)')

    started_at = models.DateTimeField(null=True, blank=True, verbose_name='开始时间')
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name='结束时间')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    report = models.JSONField(null=True, blank=True, verbose_name='面试报告')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')



    class Meta:
        verbose_name = '面试会话'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']

    def __str__(self):
        return f'面试会话: {self.job_position} ({self.user.username})'


class InterviewQuestion(models.Model):
    session = models.ForeignKey(InterviewSession, on_delete=models.CASCADE, related_name='questions',
                                verbose_name='所属会话')

    question_text = models.TextField(verbose_name='问题内容')
    sequence = models.IntegerField(verbose_name='问题序号')

    # 用户回答相关字段
    answer_text = models.TextField(blank=True, verbose_name='用户回答文本')
    audio_url = models.CharField(max_length=255, blank=True, verbose_name='回答音频 URL')

    # AI 评估相关字段
    score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, verbose_name='得分')
    ai_feedback = models.JSONField(null=True, blank=True, verbose_name='AI 反馈内容')

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    answered_at = models.DateTimeField(null=True, blank=True, verbose_name='回答时间')
    evaluated_at = models.DateTimeField(null=True, blank=True, verbose_name='评估时间')

    class Meta:
        verbose_name = '面试问题'
        verbose_name_plural = verbose_name
        ordering = ['session', 'sequence']

    def __str__(self):
        return f'问题 {self.sequence}: {self.question_text[:30]}...'