from django.db.models import Count
from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from resumes.models import Resume

from .models import ApplicationEvent, CareerFact, JobApplication, JobTarget, LearningTask
from .serializers import (
    ApplicationEventSerializer,
    CareerFactSerializer,
    JobApplicationSerializer,
    JobTargetSerializer,
    LearningTaskSerializer,
)


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
        return Response(ApplicationEventSerializer(event).data, status=status.HTTP_201_CREATED)


class LearningTaskViewSet(OwnedModelViewSet):
    queryset = LearningTask.objects.select_related('application', 'interview_session')
    serializer_class = LearningTaskSerializer
    filterset_fields = ('status', 'priority', 'dimension')


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

