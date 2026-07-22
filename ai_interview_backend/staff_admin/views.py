import hashlib
import json
import secrets
from datetime import timedelta

from django.contrib.auth.password_validation import validate_password
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone
from rest_framework import generics, permissions, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from core.throttles import LoginRateThrottle
from users.cookie_auth import enforce_csrf, ensure_csrf_token

from .authentication import StaffSessionAuthentication
from .idempotency import run_staff_idempotent
from .models import (
    AdminAuditEvent, BreakGlassGrant, StaffAccount, StaffInvitation, StaffMFADevice,
    StaffRole, StaffSession,
)
from .permissions import StaffPermission
from .security import (
    challenge_account, challenge_token, clear_staff_cookie, create_recovery_codes, create_staff_session,
    decrypt_secret, encrypt_secret, new_totp_secret, session_token_hash, set_staff_cookie, totp_uri,
    recovery_confirmation_account, recovery_confirmation_token, verify_staff_mfa, verify_totp,
)
from .serializers import AdminAuditEventSerializer, StaffAccountSerializer, StaffRoleSerializer
from .services import enqueue_staff_invitation_email


def client_ip(request):
    return (request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip() or request.META.get('REMOTE_ADDR') or None)


def audit(request, *, action, resource_type, resource_id='', reason='', before=None, after=None, metadata=None):
    previous = AdminAuditEvent.objects.order_by('-created_at', '-id').values_list('event_hash', flat=True).first() or ''
    event = AdminAuditEvent(
        actor=request.user if isinstance(request.user, StaffAccount) else None,
        action=action, resource_type=resource_type, resource_id=str(resource_id or ''),
        operation_reason=str(reason or '')[:500], request_id=getattr(request, 'request_id', ''),
        ip_address=client_ip(request), before_summary=before or {}, after_summary=after or {}, metadata=metadata or {},
        previous_hash=previous,
    )
    canonical = json.dumps({
        'id': str(event.id), 'actor': str(event.actor_id or ''), 'action': action,
        'resource_type': resource_type, 'resource_id': str(resource_id or ''),
        'reason': event.operation_reason, 'before': event.before_summary,
        'after': event.after_summary, 'metadata': event.metadata,
    }, sort_keys=True, ensure_ascii=True, separators=(',', ':'), default=str)
    event.event_hash = hashlib.sha256(f'{previous}|{canonical}'.encode()).hexdigest()
    event.save(force_insert=True)
    return event


class StaffProtectedView(APIView):
    authentication_classes = [StaffSessionAuthentication]
    permission_classes = [StaffPermission]


class StaffCsrfView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get(self, request):
        return Response({'csrf_token': ensure_csrf_token(request)})


class StaffLoginView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_classes = [LoginRateThrottle]

    def post(self, request):
        enforce_csrf(request)
        email = str(request.data.get('email') or '').strip().lower()
        password = str(request.data.get('password') or '')
        account = StaffAccount.objects.filter(email=email).first()
        now = timezone.now()
        if not account or account.status == StaffAccount.Status.SUSPENDED or (account.locked_until and account.locked_until > now) or not account.check_password(password):
            if account:
                account.failed_login_count += 1
                if account.failed_login_count >= 5:
                    account.locked_until = now + timedelta(minutes=15)
                account.save(update_fields=['failed_login_count', 'locked_until', 'updated_at'])
            return Response({'code': 'invalid_staff_credentials', 'message': '账号、密码或账号状态不正确。'}, status=status.HTTP_401_UNAUTHORIZED)
        account.failed_login_count = 0
        account.locked_until = None
        account.last_login_ip = client_ip(request)
        account.save(update_fields=['failed_login_count', 'locked_until', 'last_login_ip', 'updated_at'])
        device = account.mfa_devices.filter(confirmed_at__isnull=False).first()
        if account.must_change_password or not device or not account.recovery_codes_confirmed_at:
            return Response({
                'code': 'staff_security_setup_required', 'message': '请完成密码与双重验证设置。',
                'challenge_token': challenge_token(account),
                'requires_password_change': account.must_change_password,
                'requires_mfa_setup': not bool(device),
                'requires_recovery_confirmation': not bool(account.recovery_codes_confirmed_at),
            }, status=status.HTTP_409_CONFLICT)
        if not verify_staff_mfa(account, request.data.get('mfa_code')):
            return Response({'code': 'staff_mfa_required', 'message': '请输入有效的双重验证代码。'}, status=status.HTTP_401_UNAUTHORIZED)
        raw, _ = create_staff_session(account, request)
        account.last_login = now
        account.save(update_fields=['last_login'])
        response = Response({'account': StaffAccountSerializer(account).data})
        set_staff_cookie(response, raw)
        return response


class StaffSecuritySetupView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request):
        enforce_csrf(request)
        confirmation = str(request.data.get('recovery_confirmation_token') or '')
        if confirmation:
            try:
                account = recovery_confirmation_account(confirmation)
            except Exception:
                return Response({
                    'code': 'staff_recovery_confirmation_expired',
                    'message': '恢复码确认已过期，请重新登录。',
                }, status=400)
            if not request.data.get('recovery_codes_confirmed'):
                return Response({
                    'code': 'staff_recovery_confirmation_required',
                    'message': '请确认已安全保存恢复码。',
                }, status=400)
            device = account.mfa_devices.filter(confirmed_at__isnull=False).first()
            if not device or not account.recovery_codes.filter(used_at__isnull=True).exists():
                return Response({
                    'code': 'staff_security_setup_incomplete',
                    'message': 'MFA 或恢复码尚未完成配置。',
                }, status=409)
            account.recovery_codes_confirmed_at = timezone.now()
            account.status = StaffAccount.Status.ACTIVE
            account.save(update_fields=['recovery_codes_confirmed_at', 'status', 'updated_at'])
            raw, _ = create_staff_session(account, request)
            response = Response({'account': StaffAccountSerializer(account).data})
            set_staff_cookie(response, raw)
            return response
        try:
            account = challenge_account(str(request.data.get('challenge_token') or ''))
        except Exception:
            return Response({'code': 'staff_challenge_expired', 'message': '安全设置会话已过期。'}, status=status.HTTP_400_BAD_REQUEST)
        cache_key = f'staff_mfa_setup:{account.id}'
        device = account.mfa_devices.filter(confirmed_at__isnull=False).first()
        if not request.data.get('code'):
            if device:
                return Response({'mfa_already_configured': True, 'expires_in': 600})
            secret = new_totp_secret()
            cache.set(cache_key, secret, timeout=600)
            return Response({'secret': secret, 'otpauth_uri': totp_uri(account, secret), 'expires_in': 600})
        secret = decrypt_secret(device.encrypted_secret) if device else cache.get(cache_key)
        verified = verify_staff_mfa(account, request.data.get('code')) if device else bool(secret and verify_totp(secret, request.data.get('code')))
        if not verified:
            return Response({'code': 'staff_mfa_invalid', 'message': '双重验证代码不正确。'}, status=status.HTTP_400_BAD_REQUEST)
        new_password = str(request.data.get('new_password') or '')
        if account.must_change_password:
            if not new_password:
                return Response({'code': 'new_password_required', 'message': '请设置新的管理端密码。'}, status=status.HTTP_400_BAD_REQUEST)
            validate_password(new_password)
            account.set_password(new_password)
            account.must_change_password = False
        recovery_codes = []
        if not device:
            StaffMFADevice.objects.create(account=account, encrypted_secret=encrypt_secret(secret), confirmed_at=timezone.now())
            recovery_codes = create_recovery_codes(account)
        elif not account.recovery_codes_confirmed_at:
            recovery_codes = create_recovery_codes(account)
        account.status = StaffAccount.Status.INVITED if recovery_codes else StaffAccount.Status.ACTIVE
        account.save()
        cache.delete(cache_key)
        if recovery_codes:
            return Response({
                'recovery_codes': recovery_codes,
                'recovery_confirmation_token': recovery_confirmation_token(account),
                'confirmation_expires_in': 600,
            })
        raw, _ = create_staff_session(account, request)
        response = Response({'account': StaffAccountSerializer(account).data, 'recovery_codes': recovery_codes})
        set_staff_cookie(response, raw)
        return response


class StaffSessionView(StaffProtectedView):
    def get(self, request):
        return Response({'account': StaffAccountSerializer(request.user).data})


class StaffLogoutView(StaffProtectedView):
    def post(self, request):
        if request.auth:
            request.auth.revoked_at = timezone.now()
            request.auth.save(update_fields=['revoked_at'])
        response = Response({'message': '已退出管理端。'})
        clear_staff_cookie(response)
        return response


class AdminDashboardView(StaffProtectedView):
    required_permissions = ['dashboard.view']

    def get(self, request):
        from users.models import PrivacyRequest, User
        from knowledge.models import KnowledgeDocument
        from interviews.models import InterviewAgentRun, InterviewSession
        from core.models import AsyncOperation
        from chat.models import MessageReport
        return Response({
            'candidates': User.objects.filter(role=User.Role.CANDIDATE).count(),
            'running_interviews': InterviewSession.objects.filter(status=InterviewSession.Status.RUNNING).count(),
            'pending_knowledge_reviews': KnowledgeDocument.objects.filter(approval_status=KnowledgeDocument.ApprovalStatus.PENDING_REVIEW).count(),
            'failed_agent_runs': InterviewAgentRun.objects.filter(status=InterviewAgentRun.Status.FAILED).count(),
            'failed_tasks': AsyncOperation.objects.filter(status=AsyncOperation.Status.FAILED).count(),
            'open_message_reports': MessageReport.objects.filter(status=MessageReport.Status.OPEN).count(),
            'pending_privacy_requests': PrivacyRequest.objects.filter(status=PrivacyRequest.Status.PENDING).count(),
        })


class StaffRoleListView(generics.ListAPIView):
    authentication_classes = [StaffSessionAuthentication]
    permission_classes = [StaffPermission]
    required_permissions = ['staff.manage']
    serializer_class = StaffRoleSerializer
    queryset = StaffRole.objects.all()


class StaffAccountListCreateView(StaffProtectedView):
    required_permissions = ['staff.manage']

    def get(self, request):
        return Response(StaffAccountSerializer(StaffAccount.objects.prefetch_related('roles').all(), many=True).data)

    def post(self, request):
        reason = str(request.data.get('operation_reason') or '').strip()
        if not reason:
            return Response({'code': 'operation_reason_required', 'message': '创建员工账号必须填写操作原因。'}, status=status.HTTP_400_BAD_REQUEST)

        def execute():
            email = str(request.data.get('email') or '').strip().lower()
            role_slugs = request.data.get('roles') or []
            if not email or StaffAccount.objects.filter(email=email).exists():
                return Response({'code': 'staff_email_invalid', 'message': '邮箱为空或已存在。'}, status=status.HTTP_400_BAD_REQUEST)
            roles = list(StaffRole.objects.filter(slug__in=role_slugs))
            if not roles:
                return Response({'code': 'staff_role_required', 'message': '至少选择一个员工角色。'}, status=status.HTTP_400_BAD_REQUEST)
            with transaction.atomic():
                account = StaffAccount.objects.create_account(email=email, display_name=request.data.get('display_name') or email.split('@')[0])
                account.roles.set(roles)
                raw = secrets.token_urlsafe(40)
                StaffInvitation.objects.create(
                    account=account, token_hash=hashlib.sha256(raw.encode()).hexdigest(), invited_by=request.user,
                    expires_at=timezone.now() + timedelta(days=3),
                )
                invitation = account.invitation
                _, activation_url = enqueue_staff_invitation_email(invitation, raw)
                audit(request, action='staff.invite', resource_type='StaffAccount', resource_id=account.id, reason=reason, after={'email': email, 'roles': role_slugs})
            return Response({
                'account': StaffAccountSerializer(account).data,
                'activation_url': activation_url,
                'expires_at': invitation.expires_at,
                'delivery_status': 'pending',
            }, status=status.HTTP_201_CREATED)

        return run_staff_idempotent(request, 'staff_invite', execute)


def _last_active_super_admin(account):
    return (
        account.status == StaffAccount.Status.ACTIVE
        and account.roles.filter(slug='super_admin').exists()
        and StaffAccount.objects.filter(status=StaffAccount.Status.ACTIVE, roles__slug='super_admin').distinct().count() <= 1
    )


class StaffAccountDetailView(StaffProtectedView):
    required_permissions = ['staff.manage']

    def patch(self, request, account_id):
        reason = str(request.data.get('operation_reason') or '').strip()
        if not reason:
            return Response({'code': 'operation_reason_required', 'message': '修改员工必须填写操作原因。'}, status=400)

        def execute():
            account = StaffAccount.objects.prefetch_related('roles').filter(pk=account_id).first()
            if not account:
                return Response({'code': 'staff_not_found', 'message': '员工账号不存在。'}, status=404)
            before = StaffAccountSerializer(account).data
            role_slugs = request.data.get('roles')
            next_status = request.data.get('status')
            removes_super = role_slugs is not None and 'super_admin' not in role_slugs
            suspends = next_status == StaffAccount.Status.SUSPENDED
            if (removes_super or suspends) and _last_active_super_admin(account):
                return Response({'code': 'last_super_admin_protected', 'message': '不能停用或降级最后一个超级管理员。'}, status=409)
            if role_slugs is not None:
                roles = list(StaffRole.objects.filter(slug__in=role_slugs))
                if len(roles) != len(set(role_slugs)):
                    return Response({'code': 'staff_role_invalid', 'message': '包含不存在的员工角色。'}, status=400)
                account.roles.set(roles)
            if next_status in StaffAccount.Status.values:
                account.status = next_status
                if next_status == StaffAccount.Status.SUSPENDED:
                    account.sessions.filter(revoked_at__isnull=True).update(revoked_at=timezone.now())
            if 'display_name' in request.data:
                account.display_name = str(request.data.get('display_name') or '').strip()[:120]
            account.save()
            after = StaffAccountSerializer(account).data
            audit(request, action='staff.update', resource_type='StaffAccount', resource_id=account.id, reason=reason, before=before, after=after)
            return Response(after)

        return run_staff_idempotent(request, f'staff_update:{account_id}', execute)


class StaffAccountActionView(StaffProtectedView):
    required_permissions = ['staff.manage']

    def post(self, request, account_id, action):
        reason = str(request.data.get('operation_reason') or '').strip()
        if not reason:
            return Response({'code': 'operation_reason_required', 'message': '员工安全操作必须填写原因。'}, status=400)

        def execute():
            account = StaffAccount.objects.prefetch_related('roles').filter(pk=account_id).first()
            if not account:
                return Response({'code': 'staff_not_found', 'message': '员工账号不存在。'}, status=404)
            if action == 'revoke-sessions':
                count = account.sessions.filter(revoked_at__isnull=True).update(revoked_at=timezone.now())
                after = {'revoked_sessions': count}
            elif action == 'reset-mfa':
                account.mfa_devices.all().delete()
                account.recovery_codes.all().delete()
                account.sessions.filter(revoked_at__isnull=True).update(revoked_at=timezone.now())
                after = {'mfa_enabled': False, 'sessions_revoked': True}
            else:
                return Response({'code': 'staff_action_invalid', 'message': '不支持的员工操作。'}, status=400)
            audit(request, action=f'staff.{action}', resource_type='StaffAccount', resource_id=account.id, reason=reason, after=after)
            return Response({'id': str(account.id), **after})

        return run_staff_idempotent(request, f'staff_action:{account_id}:{action}', execute)


class StaffInvitationActionView(StaffProtectedView):
    required_permissions = ['staff.manage']

    def post(self, request, invitation_id, action):
        reason = str(request.data.get('operation_reason') or '').strip()
        if not reason:
            return Response({'code': 'operation_reason_required', 'message': '邀请操作必须填写原因。'}, status=400)

        def execute():
            invitation = StaffInvitation.objects.select_related('account').filter(pk=invitation_id).first()
            if not invitation:
                return Response({'code': 'staff_invitation_not_found', 'message': '员工邀请不存在。'}, status=404)
            if action == 'revoke':
                if invitation.status != StaffInvitation.Status.PENDING:
                    return Response({'code': 'staff_invitation_not_pending', 'message': '只能撤销待接受邀请。'}, status=409)
                invitation.status = StaffInvitation.Status.REVOKED
                invitation.revoked_at = timezone.now()
                invitation.save(update_fields=['status', 'revoked_at'])
                payload = {'status': invitation.status}
            elif action == 'resend':
                if invitation.status == StaffInvitation.Status.ACCEPTED:
                    return Response({'code': 'staff_invitation_accepted', 'message': '已接受的邀请不能重新发送。'}, status=409)
                raw = secrets.token_urlsafe(40)
                invitation.token_hash = hashlib.sha256(raw.encode()).hexdigest()
                invitation.status = StaffInvitation.Status.PENDING
                invitation.revoked_at = None
                invitation.expires_at = timezone.now() + timedelta(days=3)
                invitation.save(update_fields=['token_hash', 'status', 'revoked_at', 'expires_at'])
                _, activation_url = enqueue_staff_invitation_email(invitation, raw)
                payload = {'status': invitation.status, 'activation_url': activation_url, 'expires_at': invitation.expires_at}
            else:
                return Response({'code': 'staff_invitation_action_invalid', 'message': '不支持的邀请操作。'}, status=400)
            audit(request, action=f'staff.invitation.{action}', resource_type='StaffInvitation', resource_id=invitation.id, reason=reason, after={'status': invitation.status})
            return Response({'id': str(invitation.id), **payload})

        return run_staff_idempotent(request, f'staff_invitation:{invitation_id}:{action}', execute)


class StaffInvitationActivateView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request):
        return register_staff_invitation(request, str(request.data.get('token') or ''))


def active_invitation(raw):
    return StaffInvitation.objects.select_related('account').filter(
        token_hash=hashlib.sha256(str(raw or '').encode()).hexdigest(),
        status=StaffInvitation.Status.PENDING,
        accepted_at__isnull=True,
        expires_at__gt=timezone.now(),
    ).first()


def register_staff_invitation(request, raw):
    enforce_csrf(request)
    invitation = active_invitation(raw)
    if not invitation:
        return Response({'code': 'staff_invitation_invalid', 'message': '邀请无效、已撤销或已过期。'}, status=status.HTTP_400_BAD_REQUEST)
    password = str(request.data.get('password') or '')
    try:
        validate_password(password, user=invitation.account)
    except Exception as exc:
        messages = getattr(exc, 'messages', None) or [str(exc)]
        return Response({
            'code': 'staff_password_invalid', 'message': '密码不符合安全要求。',
            'field_errors': {'password': messages},
        }, status=status.HTTP_400_BAD_REQUEST)
    with transaction.atomic():
        invitation = StaffInvitation.objects.select_for_update().select_related('account').get(pk=invitation.pk)
        if invitation.status != StaffInvitation.Status.PENDING or invitation.expires_at <= timezone.now():
            return Response({'code': 'staff_invitation_invalid', 'message': '邀请已失效。'}, status=status.HTTP_409_CONFLICT)
        account = invitation.account
        account.display_name = str(request.data.get('display_name') or account.display_name).strip()[:120]
        account.set_password(password)
        account.must_change_password = False
        account.save(update_fields=['display_name', 'password', 'must_change_password', 'updated_at'])
        invitation.status = StaffInvitation.Status.ACCEPTED
        invitation.accepted_at = timezone.now()
        invitation.save(update_fields=['status', 'accepted_at'])
    return Response({'challenge_token': challenge_token(account), 'requires_mfa_setup': True})


class StaffInvitationDetailView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get(self, request, token):
        invitation = active_invitation(token)
        if not invitation:
            return Response({'code': 'staff_invitation_invalid', 'message': '邀请无效、已撤销或已过期。'}, status=404)
        return Response({
            'email': invitation.account.email,
            'display_name': invitation.account.display_name,
            'roles': list(invitation.account.roles.values_list('name', flat=True)),
            'expires_at': invitation.expires_at,
        })


class StaffInvitationRegisterView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request):
        return register_staff_invitation(request, str(request.data.get('invite') or ''))


class KnowledgeReviewListView(StaffProtectedView):
    required_permissions = ['knowledge.review']

    def get(self, request):
        from knowledge.models import KnowledgeDocument
        rows = KnowledgeDocument.objects.filter(approval_status=KnowledgeDocument.ApprovalStatus.PENDING_REVIEW).select_related('created_by', 'draft_revision')
        return Response([{
            'id': str(item.id), 'title': item.title, 'visibility': item.visibility, 'source_type': item.source_type,
            'parse_status': item.parse_status, 'approval_status': item.approval_status,
            'owner': item.created_by.email if item.created_by else None, 'submitted_at': item.submitted_at,
            'chunk_count': item.draft_revision.chunk_drafts.count() if item.draft_revision else 0,
        } for item in rows])


class KnowledgeReviewDecisionView(StaffProtectedView):
    required_permissions = ['knowledge.review']

    def _execute(self, request, document_id, decision):
        from knowledge.models import KnowledgeDocument, KnowledgeDocumentRevision
        from knowledge.tasks import reindex_knowledge_document
        reason = str(request.data.get('operation_reason') or '').strip()
        if not reason:
            return Response({'code': 'operation_reason_required', 'message': '审批操作必须填写原因。'}, status=status.HTTP_400_BAD_REQUEST)
        document = KnowledgeDocument.objects.select_related('draft_revision').filter(pk=document_id).first()
        revision = document.draft_revision if document else None
        if not document or not revision or revision.status != KnowledgeDocumentRevision.Status.PENDING_REVIEW:
            return Response({'code': 'knowledge_not_reviewable', 'message': '当前版本不在待审核状态。'}, status=status.HTTP_409_CONFLICT)
        before = {'approval_status': document.approval_status, 'revision_status': revision.status}
        now = timezone.now()
        if decision == 'approve':
            if document.parse_status != KnowledgeDocument.ParseStatus.PARSED:
                return Response({'code': 'knowledge_not_parsed', 'message': '文档解析完成后才能上线。'}, status=status.HTTP_409_CONFLICT)
            revision.status = KnowledgeDocumentRevision.Status.APPROVED
            revision.staff_approved_by = request.user
            revision.approved_at = now
            revision.rejection_reason = ''
            document.approval_status = KnowledgeDocument.ApprovalStatus.APPROVED
            document.staff_approved_by = request.user
            document.approved_at = now
            document.status = KnowledgeDocument.Status.INDEXING
            document.rejection_reason = ''
            revision.save()
            document.save()
            transaction.on_commit(lambda: reindex_knowledge_document.delay(str(document.id), str(revision.id)))
        elif decision == 'reject':
            revision.status = KnowledgeDocumentRevision.Status.REJECTED
            revision.staff_approved_by = request.user
            revision.rejection_reason = reason
            document.approval_status = KnowledgeDocument.ApprovalStatus.REJECTED if not document.published_revision_id else document.approval_status
            document.rejection_reason = reason
            revision.save()
            document.save()
        else:
            return Response({'code': 'invalid_review_decision', 'message': '审批动作无效。'}, status=status.HTTP_400_BAD_REQUEST)
        audit(request, action=f'knowledge.{decision}', resource_type='KnowledgeDocument', resource_id=document.id, reason=reason, before=before, after={'approval_status': document.approval_status, 'revision_status': revision.status})
        return Response({'id': str(document.id), 'approval_status': document.approval_status, 'index_status': document.status})

    def post(self, request, document_id, decision):
        return run_staff_idempotent(
            request,
            f'knowledge_review:{document_id}:{decision}',
            lambda: self._execute(request, document_id, decision),
        )


class AgentRunListView(StaffProtectedView):
    required_permissions = ['interview.audit']

    def get(self, request):
        from interviews.models import InterviewAgentRun
        rows = InterviewAgentRun.objects.select_related('session').order_by('-created_at')[:100]
        return Response([{
            'run_id': str(item.id), 'session_id': str(item.session_id), 'event': item.event,
            'status': item.status, 'current_node': item.current_node, 'attempt_count': item.attempt_count,
            'fallback_reason': item.fallback_reason, 'created_at': item.created_at, 'completed_at': item.completed_at,
        } for item in rows])


class ModelGatewaySummaryView(StaffProtectedView):
    required_permissions = ['gateway.manage']

    def get(self, request):
        from system.models import ModelDeployment, ModelRequestLedger, ProviderCredential, UsageBudget
        today = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        return Response({
            'deployments': ModelDeployment.objects.count(), 'healthy_deployments': ModelDeployment.objects.filter(last_health_status='healthy').count(),
            'active_credentials': ProviderCredential.objects.filter(is_active=True).count(),
            'requests_today': ModelRequestLedger.objects.filter(created_at__gte=today).count(),
            'failed_requests_today': ModelRequestLedger.objects.filter(created_at__gte=today, status=ModelRequestLedger.Status.FAILED).count(),
            'active_budgets': UsageBudget.objects.filter(is_active=True).count(),
        })


class AdminTaskListView(StaffProtectedView):
    required_permissions = ['tasks.manage']

    def get(self, request):
        from core.models import AsyncOperation
        rows = AsyncOperation.objects.select_related('user').order_by('-created_at')
        status_filter = request.query_params.get('status')
        if status_filter:
            rows = rows.filter(status=status_filter)
        rows = rows[:200]
        return Response([{
            'id': str(item.id), 'operation_type': item.operation_type, 'title': item.title,
            'status': item.status, 'progress': item.progress, 'retryable': item.retryable,
            'error_code': item.error_code, 'error_message': item.error_message,
            'owner_id': item.user_id, 'owner_email': item.user.email,
            'created_at': item.created_at, 'updated_at': item.updated_at,
        } for item in rows])


class AdminSystemHealthView(StaffProtectedView):
    required_permissions = ['system.health']

    def get(self, request):
        from system.views import SystemReadinessView
        return SystemReadinessView().get(request)


class CandidateAccountListView(StaffProtectedView):
    required_permissions = ['candidate.support']

    def get(self, request):
        from users.models import User
        rows = User.objects.filter(role=User.Role.CANDIDATE).order_by('-date_joined')
        search = str(request.query_params.get('search') or '').strip()
        if search:
            rows = rows.filter(email__icontains=search)
        rows = rows[:200]
        return Response([{
            'id': item.id, 'email': item.email, 'username': item.username,
            'status': item.status, 'onboarding_completed': bool(item.onboarding_completed_at),
            'last_login': item.last_login, 'created_at': item.date_joined,
        } for item in rows])


class CandidateAccountDetailView(StaffProtectedView):
    required_permissions = ['candidate.support']

    def get(self, request, candidate_id):
        from careers.models import JobApplication, JobTarget
        from interviews.models import InterviewSession
        from resumes.models import Resume
        from users.models import AuthSession, LoginAudit, PrivacyRequest, User
        candidate = User.objects.filter(pk=candidate_id, role=User.Role.CANDIDATE).first()
        if not candidate:
            return Response({'code': 'candidate_not_found', 'message': '候选人不存在。'}, status=404)
        return Response({
            'id': candidate.id, 'email': candidate.email, 'username': candidate.username,
            'status': candidate.status, 'profile_visibility': candidate.profile_visibility,
            'onboarding_completed': bool(candidate.onboarding_completed_at),
            'last_login': candidate.last_login, 'created_at': candidate.date_joined,
            'counts': {
                'resumes': Resume.objects.filter(user=candidate).count(),
                'interviews': InterviewSession.objects.filter(user=candidate).count(),
                'job_targets': JobTarget.objects.filter(user=candidate).count(),
                'applications': JobApplication.objects.filter(user=candidate).count(),
                'active_sessions': AuthSession.objects.filter(user=candidate, revoked_at__isnull=True, expires_at__gt=timezone.now()).count(),
                'privacy_requests': PrivacyRequest.objects.filter(user=candidate).count(),
            },
            'recent_logins': list(LoginAudit.objects.filter(user=candidate).values(
                'event', 'success', 'ip_address', 'reason', 'created_at',
            )[:20]),
            'private_content_access': 'break_glass_required',
        })


class CandidateAccountActionView(StaffProtectedView):
    required_permissions = ['candidate.support']

    def post(self, request, candidate_id, action):
        from users.models import AuthSession, User
        reason = str(request.data.get('operation_reason') or '').strip()
        if not reason:
            return Response({'code': 'operation_reason_required', 'message': '候选人账号操作必须填写原因。'}, status=400)

        def execute():
            candidate = User.objects.filter(pk=candidate_id, role=User.Role.CANDIDATE).first()
            if not candidate:
                return Response({'code': 'candidate_not_found', 'message': '候选人不存在。'}, status=404)
            before = {'status': candidate.status}
            if action == 'suspend':
                candidate.status = User.Status.DISABLED
                candidate.is_active = False
                candidate.save(update_fields=['status', 'is_active', 'updated_at'])
                AuthSession.objects.filter(user=candidate, revoked_at__isnull=True).update(revoked_at=timezone.now())
            elif action == 'reactivate':
                candidate.status = User.Status.NORMAL
                candidate.is_active = True
                candidate.save(update_fields=['status', 'is_active', 'updated_at'])
            elif action == 'revoke-sessions':
                count = AuthSession.objects.filter(user=candidate, revoked_at__isnull=True).update(revoked_at=timezone.now())
                audit(request, action='candidate.revoke-sessions', resource_type='User', resource_id=candidate.id, reason=reason, after={'revoked_sessions': count})
                return Response({'id': candidate.id, 'revoked_sessions': count})
            else:
                return Response({'code': 'candidate_action_invalid', 'message': '不支持的候选人操作。'}, status=400)
            audit(request, action=f'candidate.{action}', resource_type='User', resource_id=candidate.id, reason=reason, before=before, after={'status': candidate.status})
            return Response({'id': candidate.id, 'status': candidate.status})

        return run_staff_idempotent(request, f'candidate_action:{candidate_id}:{action}', execute)


class CandidateBreakGlassView(StaffProtectedView):
    required_permissions = ['candidate.private_access']

    def post(self, request, candidate_id):
        reason = str(request.data.get('operation_reason') or '').strip()
        if len(reason) < 10:
            return Response({'code': 'break_glass_reason_required', 'message': '请填写不少于 10 个字的访问原因。'}, status=400)

        def execute():
            from users.models import User
            if not verify_staff_mfa(request.user, request.data.get('mfa_code')):
                return Response({'code': 'staff_reauthentication_failed', 'message': 'MFA 二次验证失败。'}, status=403)
            if not User.objects.filter(pk=candidate_id, role=User.Role.CANDIDATE).exists():
                return Response({'code': 'candidate_not_found', 'message': '候选人不存在。'}, status=404)
            grant = BreakGlassGrant.objects.create(
                account=request.user, candidate_id=candidate_id, operation_reason=reason,
                expires_at=timezone.now() + timedelta(minutes=15),
            )
            audit(
                request, action='candidate.break_glass.grant', resource_type='User', resource_id=candidate_id,
                reason=reason, after={'grant_id': str(grant.id), 'expires_at': grant.expires_at},
            )
            return Response({'grant_id': str(grant.id), 'expires_at': grant.expires_at, 'scope': grant.scope})

        return run_staff_idempotent(request, f'candidate_break_glass:{candidate_id}', execute)


class PrivacyRequestListView(StaffProtectedView):
    required_permissions = ['privacy.manage']

    def get(self, request):
        from users.models import PrivacyRequest
        rows = PrivacyRequest.objects.select_related('user').order_by('-created_at')[:200]
        status_filter = request.query_params.get('status')
        if status_filter:
            rows = rows.filter(status=status_filter)
        return Response([{
            'id': item.id, 'request_type': item.request_type, 'status': item.status,
            'user_id': item.user_id, 'user_email': item.user.email,
            'reason': item.reason, 'created_at': item.created_at, 'completed_at': item.completed_at,
        } for item in rows])


class PrivacyRequestDecisionView(StaffProtectedView):
    required_permissions = ['privacy.manage']

    def post(self, request, request_id, decision):
        from users.models import PrivacyRequest
        reason = str(request.data.get('operation_reason') or '').strip()
        if not reason:
            return Response({'code': 'operation_reason_required', 'message': '隐私请求处理必须填写原因。'}, status=400)

        def execute():
            item = PrivacyRequest.objects.select_related('user').filter(pk=request_id).first()
            if not item:
                return Response({'code': 'privacy_request_not_found', 'message': '隐私请求不存在。'}, status=404)
            if item.status != PrivacyRequest.Status.PENDING:
                return Response({'code': 'privacy_request_closed', 'message': '该隐私请求已经处理。'}, status=409)
            if decision not in {'complete', 'reject'}:
                return Response({'code': 'privacy_decision_invalid', 'message': '处理动作无效。'}, status=400)
            item.status = PrivacyRequest.Status.COMPLETED if decision == 'complete' else PrivacyRequest.Status.REJECTED
            item.completed_at = timezone.now()
            item.result = {**(item.result or {}), 'staff_note': reason}
            item.save(update_fields=['status', 'completed_at', 'result'])
            audit(request, action=f'privacy.{decision}', resource_type='PrivacyRequest', resource_id=item.id, reason=reason, after={'status': item.status})
            return Response({'id': item.id, 'status': item.status, 'completed_at': item.completed_at})

        return run_staff_idempotent(request, f'privacy_request:{request_id}:{decision}', execute)


class ModerationReportListView(StaffProtectedView):
    required_permissions = ['moderation.manage']

    def get(self, request):
        from chat.models import MessageReport
        rows = MessageReport.objects.select_related('reporter', 'message', 'message__sender').order_by('-created_at')[:100]
        return Response([{
            'id': item.id, 'status': item.status, 'reason': item.reason, 'detail': item.detail,
            'reporter': item.reporter.email, 'sender': item.message.sender.email,
            'message_id': item.message_id, 'created_at': item.created_at,
        } for item in rows])


class ModerationReportDecisionView(StaffProtectedView):
    required_permissions = ['moderation.manage']

    def post(self, request, report_id, decision):
        from chat.models import MessageReport
        reason = str(request.data.get('operation_reason') or '').strip()
        if not reason:
            return Response({'code': 'operation_reason_required', 'message': '处理举报必须填写操作原因。'}, status=status.HTTP_400_BAD_REQUEST)

        def execute():
            report = MessageReport.objects.filter(pk=report_id).first()
            if not report:
                return Response({'code': 'report_not_found', 'message': '举报记录不存在。'}, status=status.HTTP_404_NOT_FOUND)
            if decision not in {'resolve', 'reject'}:
                return Response({'code': 'invalid_moderation_decision', 'message': '处理动作无效。'}, status=status.HTTP_400_BAD_REQUEST)
            before = {'status': report.status}
            report.status = MessageReport.Status.RESOLVED if decision == 'resolve' else MessageReport.Status.REJECTED
            report.resolved_at = timezone.now()
            report.save(update_fields=['status', 'resolved_at'])
            audit(
                request, action=f'moderation.{decision}', resource_type='MessageReport',
                resource_id=report.id, reason=reason, before=before, after={'status': report.status},
            )
            return Response({'id': report.id, 'status': report.status})

        return run_staff_idempotent(request, f'moderation_report:{report_id}:{decision}', execute)


class AdminAuditListView(generics.ListAPIView):
    authentication_classes = [StaffSessionAuthentication]
    permission_classes = [StaffPermission]
    required_permissions = ['audit.view']
    serializer_class = AdminAuditEventSerializer
    queryset = AdminAuditEvent.objects.select_related('actor').all()
