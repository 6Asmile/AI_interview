from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from core.events import enqueue_integration_event
from core.admission import admit_expensive_operation
from core.idempotency import run_idempotent
from core.models import AsyncOperation
from resumes.models import Resume
from resumes.models import ResumeVersion

from .models import (
    AbilitySnapshot,
    ApplicationEvent,
    CareerFact,
    CareerProfile,
    CareerTimelineEvent,
    Company,
    CompanyMember,
    CompanyVerification,
    JobApplication,
    JobMatchAnalysis,
    JobPosting,
    JobPostingRevision,
    JobTarget,
    LearningPlan,
    LearningTask,
    WeeklyCareerReport,
)
from .serializers import (
    AbilitySnapshotSerializer,
    ApplicationEventSerializer,
    CareerFactSerializer,
    CareerProfileSerializer,
    CareerTimelineEventSerializer,
    CompanyMemberSerializer,
    CompanySerializer,
    JobApplicationSerializer,
    JobMatchAnalysisSerializer,
    JobPostingRevisionSerializer,
    JobPostingSerializer,
    JobTargetSerializer,
    LearningPlanSerializer,
    LearningTaskSerializer,
    WeeklyCareerReportSerializer,
)
from .services import create_learning_plan, record_timeline_event, save_posting_as_target, stable_hash
from .tasks import run_job_match_analysis


class OwnedModelViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    owner_field = 'user'

    def get_queryset(self):
        return self.queryset.filter(**{self.owner_field: self.request.user})

    def perform_create(self, serializer):
        serializer.save(**{self.owner_field: self.request.user})


class CareerFactViewSet(OwnedModelViewSet):
    queryset = CareerFact.objects.all()
    serializer_class = CareerFactSerializer
    filterset_fields = ('fact_type', 'verification_status', 'source_type')

    @action(detail=True, methods=['post'])
    def confirm(self, request, pk=None):
        fact = self.get_object()
        fact.verification_status = CareerFact.VerificationStatus.CONFIRMED
        fact.verified_at = timezone.now()
        fact.save(update_fields=['verification_status', 'verified_at', 'updated_at'])
        record_timeline_event(
            user=request.user,
            event_type='career.fact.confirmed',
            title=f'确认职业事实：{fact.title}',
            source_type='CareerFact',
            source_id=fact.pk,
        )
        enqueue_integration_event(
            event_type='career.fact.confirmed',
            producer='careers',
            aggregate_type='CareerFact',
            aggregate_id=fact.pk,
            actor_id=request.user.pk,
            payload={'career_fact_id': fact.pk, 'verification_status': fact.verification_status},
        )
        return Response(self.get_serializer(fact).data)

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        fact = self.get_object()
        fact.verification_status = CareerFact.VerificationStatus.REJECTED
        fact.verified_at = None
        fact.save(update_fields=['verification_status', 'verified_at', 'updated_at'])
        return Response(self.get_serializer(fact).data)


class JobTargetViewSet(OwnedModelViewSet):
    queryset = JobTarget.objects.all()
    serializer_class = JobTargetSerializer
    filterset_fields = ('status',)
    search_fields = ('company_name', 'position_name', 'jd_text')

    def get_queryset(self):
        return super().get_queryset().annotate(application_count=Count('applications'))

    def perform_create(self, serializer):
        jd_text = serializer.validated_data.get('jd_text', '')
        serializer.save(
            user=self.request.user,
            source_type=JobTarget.SourceType.MANUAL,
            jd_snapshot_hash=stable_hash({'jd_text': jd_text}),
        )

    @action(detail=True, methods=['post'], url_path='match-analyses')
    def create_match_analysis(self, request, pk=None):
        target = self.get_object()
        admit_expensive_operation(request, scope='job-match')

        def create_operation():
            resume_version_id = request.data.get('resume_version_id')
            try:
                resume_version = ResumeVersion.objects.select_related('resume').get(
                    pk=resume_version_id,
                    resume__user=request.user,
                )
            except ResumeVersion.DoesNotExist:
                raise ValidationError({'resume_version_id': '简历版本不存在或无权访问。'})
            with transaction.atomic():
                operation = AsyncOperation.objects.create(
                    user=request.user,
                    operation_type='job_match_analysis',
                    source_app='careers',
                    source_model='JobTarget',
                    source_id=f'{target.pk}:{resume_version.pk}:{timezone.now().timestamp()}',
                    title=f'分析 {target.position_name} 岗位匹配度',
                )
                analysis = JobMatchAnalysis.objects.create(
                    user=request.user,
                    job_target=target,
                    resume_version=resume_version,
                    job_posting_revision=target.job_posting_revision,
                    operation=operation,
                    jd_snapshot=target.jd_text,
                    jd_snapshot_hash=target.jd_snapshot_hash or stable_hash({'jd_text': target.jd_text}),
                    config_snapshot={'engine': 'ifaceoff-resume-fit/1.0'},
                    config_hash=stable_hash({'engine': 'ifaceoff-resume-fit/1.0'}),
                )
                transaction.on_commit(lambda: run_job_match_analysis.delay(str(analysis.pk)))
            return Response({
                'operation_id': str(operation.pk),
                'status': 'accepted',
                'events_url': f'/api/v2/operations/{operation.pk}/events/',
                'result_url': f'/api/v2/operations/{operation.pk}/',
                'analysis_id': str(analysis.pk),
            }, status=status.HTTP_202_ACCEPTED)

        return run_idempotent(
            request,
            f'career.job_target.{target.pk}.match_analysis',
            create_operation,
            required=True,
        )

    @action(detail=True, methods=['post'], url_path='interview-sessions')
    def create_interview_session(self, request, pk=None):
        target = self.get_object()
        admit_expensive_operation(request, scope='interview-start')
        from interviews.views import InterviewSessionViewSet
        return run_idempotent(
            request,
            f'career.job_target.{target.pk}.interview_session',
            lambda: InterviewSessionViewSet()._start_interview_impl(
                request,
                overrides={
                    'job_target_id': target.pk,
                    'job_position': target.position_name,
                    'jd_text': target.jd_text,
                },
            ),
            required=True,
        )


class JobApplicationViewSet(OwnedModelViewSet):
    queryset = JobApplication.objects.select_related('job_target', 'resume_version', 'resume_version__resume').prefetch_related('events')
    serializer_class = JobApplicationSerializer
    filterset_fields = ('status', 'job_target')
    search_fields = ('job_target__company_name', 'job_target__position_name', 'notes')

    @action(detail=True, methods=['post'], url_path='events')
    def add_event(self, request, pk=None):
        application = self.get_object()
        serializer = ApplicationEventSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        event = serializer.save(application=application)
        record_timeline_event(
            user=request.user,
            event_type='application.status.changed',
            title=f'更新投递：{application.job_target.position_name}',
            source_type='ApplicationEvent',
            source_id=event.pk,
            summary=event.notes,
            metadata={'status': application.status, 'stage': event.stage},
            occurred_at=event.occurred_at,
        )
        enqueue_integration_event(
            event_type='application.status.changed',
            producer='careers',
            aggregate_type='JobApplication',
            aggregate_id=application.pk,
            actor_id=request.user.pk,
            payload={'application_id': application.pk, 'status': application.status, 'event_id': event.pk},
        )
        return Response(ApplicationEventSerializer(event).data, status=status.HTTP_201_CREATED)


class LearningTaskViewSet(OwnedModelViewSet):
    queryset = LearningTask.objects.select_related('application', 'interview_session')
    serializer_class = LearningTaskSerializer
    filterset_fields = ('status', 'priority', 'dimension')

    def perform_update(self, serializer):
        previous_status = serializer.instance.status
        task = serializer.save()
        if previous_status != LearningTask.Status.DONE and task.status == LearningTask.Status.DONE:
            record_timeline_event(
                user=self.request.user,
                event_type='learning.task.completed',
                title=f'完成学习任务：{task.title}',
                source_type='LearningTask',
                source_id=task.pk,
            )
            enqueue_integration_event(
                event_type='learning.task.completed',
                producer='careers',
                aggregate_type='LearningTask',
                aggregate_id=task.pk,
                actor_id=self.request.user.pk,
                payload={'learning_task_id': task.pk, 'plan_id': str(task.plan_id or '')},
            )


class CareerProfileView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self, user):
        return CareerProfile.objects.get_or_create(user=user)[0]

    def get(self, request):
        return Response(CareerProfileSerializer(self.get_object(request.user)).data)

    def patch(self, request):
        profile = self.get_object(request.user)
        serializer = CareerProfileSerializer(profile, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    put = patch


class OwnedReadOnlyViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    owner_field = 'user'

    def get_queryset(self):
        return self.queryset.filter(**{self.owner_field: self.request.user})


class CareerTimelineViewSet(OwnedReadOnlyViewSet):
    queryset = CareerTimelineEvent.objects.all()
    serializer_class = CareerTimelineEventSerializer
    filterset_fields = ('event_type', 'source_type')


class AbilitySnapshotViewSet(OwnedReadOnlyViewSet):
    queryset = AbilitySnapshot.objects.all()
    serializer_class = AbilitySnapshotSerializer
    filterset_fields = ('trigger',)


class WeeklyCareerReportViewSet(OwnedReadOnlyViewSet):
    queryset = WeeklyCareerReport.objects.all()
    serializer_class = WeeklyCareerReportSerializer


class JobMatchAnalysisViewSet(OwnedReadOnlyViewSet):
    queryset = JobMatchAnalysis.objects.select_related('job_target', 'resume_version')
    serializer_class = JobMatchAnalysisSerializer
    filterset_fields = ('status', 'job_target', 'resume_version')

    @action(detail=True, methods=['post'], url_path='learning-plan')
    def learning_plan(self, request, pk=None):
        analysis = self.get_object()
        return run_idempotent(
            request,
            f'career.match_analysis.{analysis.pk}.learning_plan',
            lambda: Response(
                LearningPlanSerializer(
                    create_learning_plan(analysis=analysis, user=request.user)
                ).data,
                status=status.HTTP_201_CREATED,
            ),
            required=True,
        )


class LearningPlanViewSet(OwnedReadOnlyViewSet):
    queryset = LearningPlan.objects.prefetch_related('tasks')
    serializer_class = LearningPlanSerializer
    filterset_fields = ('status', 'job_target')


class PublicCompanyViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [permissions.AllowAny]
    queryset = Company.objects.filter(status=Company.Status.VERIFIED)
    serializer_class = CompanySerializer
    filterset_fields = ('industry', 'location')
    search_fields = ('name', 'description', 'industry')


class PublicJobPostingViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [permissions.AllowAny]
    queryset = JobPosting.objects.filter(
        status=JobPosting.Status.PUBLISHED,
        company__status=Company.Status.VERIFIED,
    ).select_related('company', 'current_revision')
    serializer_class = JobPostingSerializer
    filterset_fields = ('company', 'location', 'work_mode', 'employment_type')
    search_fields = ('title', 'current_revision__jd_text', 'company__name')

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated], url_path='save-as-target')
    def save_as_target(self, request, pk=None):
        posting = self.get_object()
        return run_idempotent(
            request,
            f'career.job_posting.{posting.pk}.save_target',
            lambda: Response(
                JobTargetSerializer(save_posting_as_target(posting=posting, user=request.user)).data,
                status=status.HTTP_201_CREATED,
            ),
            required=True,
        )


class EmployerCompanyViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = CompanySerializer

    def get_queryset(self):
        return Company.objects.filter(
            Q(created_by=self.request.user) |
            Q(members__user=self.request.user, members__status=CompanyMember.Status.ACTIVE)
        ).distinct()

    def perform_create(self, serializer):
        company = serializer.save(created_by=self.request.user)
        CompanyMember.objects.create(
            company=company,
            user=self.request.user,
            role=CompanyMember.Role.OWNER,
        )

    @action(detail=True, methods=['get', 'post'])
    def members(self, request, pk=None):
        company = self.get_object()
        memberships = company.members.select_related('user')
        if request.method == 'GET':
            return Response(CompanyMemberSerializer(memberships, many=True).data)
        if not memberships.filter(
            user=request.user,
            role=CompanyMember.Role.OWNER,
            status=CompanyMember.Status.ACTIVE,
        ).exists():
            self.permission_denied(request, message='只有企业所有者可以管理成员。')

        def create_member():
            serializer = CompanyMemberSerializer(data={**request.data, 'company': str(company.pk)})
            serializer.is_valid(raise_exception=True)
            member = serializer.save(company=company)
            return Response(CompanyMemberSerializer(member).data, status=status.HTTP_201_CREATED)

        return run_idempotent(
            request,
            f'employer.company.{company.pk}.member',
            create_member,
            required=True,
        )

    @action(detail=True, methods=['post'], url_path='submit-verification')
    def submit_verification(self, request, pk=None):
        company = self.get_object()
        if not company.members.filter(
            user=request.user,
            role=CompanyMember.Role.OWNER,
            status=CompanyMember.Status.ACTIVE,
        ).exists():
            self.permission_denied(request, message='只有企业所有者可以提交认证。')

        def create_verification():
            verification = CompanyVerification.objects.create(
                company=company,
                status=CompanyVerification.Status.SUBMITTED,
                evidence=request.data.get('evidence') or [],
                operation_reason=str(request.data.get('operation_reason') or '')[:500],
                submitted_by=request.user,
                submitted_at=timezone.now(),
            )
            company.status = Company.Status.PENDING
            company.save(update_fields=['status', 'updated_at'])
            return Response({'verification_id': str(verification.pk), 'status': verification.status}, status=status.HTTP_202_ACCEPTED)

        return run_idempotent(
            request,
            f'employer.company.{company.pk}.verification',
            create_verification,
            required=True,
        )


class EmployerJobPostingViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = JobPostingSerializer

    def get_queryset(self):
        return JobPosting.objects.filter(
            company__members__user=self.request.user,
            company__members__status=CompanyMember.Status.ACTIVE,
        ).select_related('company', 'current_revision').distinct()

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=['post'], url_path='revisions')
    def create_revision(self, request, pk=None):
        posting = self.get_object()

        def create():
            serializer = JobPostingRevisionSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            with transaction.atomic():
                version = (posting.revisions.order_by('-version').values_list('version', flat=True).first() or 0) + 1
                payload = serializer.validated_data
                revision = serializer.save(
                    posting=posting,
                    version=version,
                    title=payload.get('title') or posting.title,
                    content_hash=stable_hash(payload),
                    created_by=request.user,
                )
                posting.current_revision = revision
                posting.title = revision.title
                posting.status = JobPosting.Status.PENDING
                posting.save(update_fields=['current_revision', 'title', 'status', 'updated_at'])
            return Response(JobPostingRevisionSerializer(revision).data, status=status.HTTP_201_CREATED)

        return run_idempotent(
            request,
            f'employer.job_posting.{posting.pk}.revision',
            create,
            required=True,
        )


class CareerDashboardView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        applications = JobApplication.objects.filter(user=request.user)
        pipeline = {item['status']: item['count'] for item in applications.values('status').annotate(count=Count('id'))}
        upcoming = applications.filter(next_action_at__isnull=False, next_action_at__gte=timezone.now()).select_related('job_target').order_by('next_action_at')[:5]
        tasks = LearningTask.objects.filter(user=request.user).exclude(status=LearningTask.Status.DONE)
        resumes = Resume.objects.filter(user=request.user)
        return Response({
            'pipeline': pipeline,
            'active_job_targets': JobTarget.objects.filter(user=request.user, status=JobTarget.Status.ACTIVE).count(),
            'confirmed_facts': CareerFact.objects.filter(user=request.user, verification_status=CareerFact.VerificationStatus.CONFIRMED).count(),
            'resume_count': resumes.count(),
            'resumes_without_versions': resumes.filter(current_version__isnull=True).count(),
            'open_learning_tasks': tasks.count(),
            'upcoming_actions': [
                {
                    'application_id': item.id,
                    'company_name': item.job_target.company_name,
                    'position_name': item.job_target.position_name,
                    'next_action_at': item.next_action_at,
                    'status': item.status,
                }
                for item in upcoming
            ],
        })
