import base64
import hashlib
import logging
import secrets
from datetime import timedelta
from urllib.parse import urlencode

import requests
from allauth.socialaccount.models import SocialAccount, SocialApp
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.http import HttpResponseRedirect
from django.utils import timezone
from requests.exceptions import RequestException
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .cookie_auth import enforce_csrf, set_refresh_cookie
from .models import LoginAudit, OAuthFlow
from .token_views import record_auth_session

logger = logging.getLogger(__name__)
User = get_user_model()


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _pkce_challenge(verifier: str) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')


def _client_config() -> tuple[str, str]:
    client_id = str(getattr(settings, 'GITHUB_CLIENT_ID', '') or '').strip()
    client_secret = str(getattr(settings, 'GITHUB_CLIENT_SECRET', '') or '').strip()
    if client_id and client_secret:
        return client_id, client_secret
    app = SocialApp.objects.filter(provider='github').order_by('id').first()
    if not app:
        raise RuntimeError('github_oauth_not_configured')
    return app.client_id, app.secret


def _safe_return_to(value: str | None) -> str:
    path = str(value or '/dashboard').strip()
    return path if path.startswith('/') and not path.startswith('//') else '/dashboard'


def _frontend_callback(**params) -> str:
    base = str(getattr(settings, 'PUBLIC_FRONTEND_URL', 'http://127.0.0.1:5173')).rstrip('/')
    return f'{base}/oauth/callback?{urlencode(params)}'


def _mask_email(email: str) -> str:
    local, _, domain = email.partition('@')
    visible = local[:2] if len(local) > 2 else local[:1]
    return f'{visible}***@{domain}'


def _profile(access_token: str) -> tuple[str, str, str | None, dict]:
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
    }
    user_response = requests.get('https://api.github.com/user', headers=headers, timeout=15)
    user_response.raise_for_status()
    payload = user_response.json()
    uid = str(payload.get('id') or '')
    if not uid:
        raise ValueError('github_profile_missing_id')

    email_response = requests.get('https://api.github.com/user/emails', headers=headers, timeout=15)
    email_response.raise_for_status()
    verified = [item for item in email_response.json() if item.get('verified') and item.get('email')]
    primary = next((item for item in verified if item.get('primary')), None)
    email = str((primary or (verified[0] if verified else {})).get('email') or '').strip().lower() or None
    username = str(payload.get('login') or f'github_{uid}')
    safe_profile = {
        'id': payload.get('id'),
        'login': payload.get('login'),
        'name': payload.get('name'),
        'avatar_url': payload.get('avatar_url'),
        'html_url': payload.get('html_url'),
    }
    return uid, username, email, safe_profile


def _unique_username(preferred: str, uid: str) -> str:
    base = ''.join(char for char in preferred if char.isalnum() or char in {'_', '-'})[:120] or f'github_{uid}'
    candidate = base
    suffix = 0
    while User.objects.filter(username__iexact=candidate).exists():
        suffix += 1
        candidate = f'{base[:120]}_{uid}' if suffix == 1 else f'{base[:110]}_{uid}_{suffix}'
    return candidate[:150]


def _login_response(request, user, *, event: str) -> Response:
    refresh = RefreshToken.for_user(user)
    record_auth_session(user, refresh, request, event=event)
    response = Response({
        'access': str(refresh.access_token),
        'auth_mode': 'cookie_refresh',
    })
    set_refresh_cookie(response, str(refresh))
    return response


def _redirect_with_session(request, user, flow: OAuthFlow, *, event: str) -> HttpResponseRedirect:
    refresh = RefreshToken.for_user(user)
    record_auth_session(user, refresh, request, event=event)
    response = HttpResponseRedirect(_frontend_callback(status='success', flow=flow.flow, next=flow.return_to))
    set_refresh_cookie(response, str(refresh))
    return response


def _record_login(request, *, email='', user=None, success=False, reason=''):
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip()
    LoginAudit.objects.create(
        user=user,
        email=email,
        event='github_login',
        success=success,
        ip_address=forwarded or request.META.get('REMOTE_ADDR') or None,
        user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
        reason=str(reason or '')[:160],
    )


class GitHubOAuthStartView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        flow_name = str(request.query_params.get('flow') or OAuthFlow.Flow.LOGIN)
        if flow_name not in OAuthFlow.Flow.values:
            return Response({'code': 'oauth_flow_invalid', 'message': '不支持的 GitHub 授权流程。'}, status=400)
        if flow_name == OAuthFlow.Flow.CONNECT and not request.user.is_authenticated:
            return Response({'code': 'authentication_required', 'message': '登录后才能绑定 GitHub。'}, status=401)
        try:
            client_id, _ = _client_config()
        except RuntimeError:
            return Response({'code': 'github_oauth_not_configured', 'message': 'GitHub 登录尚未配置。'}, status=503)

        OAuthFlow.objects.filter(
            status__in=[OAuthFlow.Status.PENDING, OAuthFlow.Status.PROCESSING, OAuthFlow.Status.LINK_REQUIRED],
            expires_at__lte=timezone.now(),
        ).update(status=OAuthFlow.Status.FAILED, error_code='oauth_expired', completed_at=timezone.now())
        raw_state = secrets.token_urlsafe(40)
        verifier = secrets.token_urlsafe(64)
        redirect_uri = str(getattr(settings, 'GITHUB_OAUTH_CALLBACK_URL', '')).strip()
        OAuthFlow.objects.create(
            flow=flow_name,
            state_hash=_digest(raw_state),
            code_verifier=verifier,
            redirect_uri=redirect_uri,
            return_to=_safe_return_to(request.query_params.get('return_to')),
            requested_user=request.user if flow_name == OAuthFlow.Flow.CONNECT else None,
            expires_at=timezone.now() + timedelta(minutes=10),
        )
        authorize_url = 'https://github.com/login/oauth/authorize?' + urlencode({
            'client_id': client_id,
            'redirect_uri': redirect_uri,
            'scope': 'read:user user:email',
            'state': raw_state,
            'code_challenge': _pkce_challenge(verifier),
            'code_challenge_method': 'S256',
        })
        return Response({'authorize_url': authorize_url, 'expires_in': 600})


class GitHubOAuthCallbackView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get(self, request):
        raw_state = str(request.query_params.get('state') or '')
        error = str(request.query_params.get('error') or '')
        code = str(request.query_params.get('code') or '')
        if not raw_state:
            return HttpResponseRedirect(_frontend_callback(status='error', code='oauth_state_missing'))
        with transaction.atomic():
            flow = OAuthFlow.objects.select_for_update().filter(
                state_hash=_digest(raw_state),
                status=OAuthFlow.Status.PENDING,
                expires_at__gt=timezone.now(),
            ).first()
            if not flow:
                return HttpResponseRedirect(_frontend_callback(status='error', code='oauth_state_invalid'))
            if error or not code:
                flow.status = OAuthFlow.Status.FAILED
                flow.error_code = 'oauth_cancelled' if error == 'access_denied' else 'oauth_code_missing'
                flow.completed_at = timezone.now()
                flow.save(update_fields=['status', 'error_code', 'completed_at'])
                return HttpResponseRedirect(_frontend_callback(status='error', code=flow.error_code))
            flow.status = OAuthFlow.Status.PROCESSING
            flow.save(update_fields=['status'])

        try:
            client_id, client_secret = _client_config()
            token_response = requests.post(
                'https://github.com/login/oauth/access_token',
                data={
                    'client_id': client_id,
                    'client_secret': client_secret,
                    'code': code,
                    'redirect_uri': flow.redirect_uri,
                    'code_verifier': flow.code_verifier,
                },
                headers={'Accept': 'application/json'},
                timeout=15,
            )
            token_response.raise_for_status()
            token_payload = token_response.json()
            if token_payload.get('error') or not token_payload.get('access_token'):
                raise ValueError('github_token_exchange_failed')
            uid, username, email, profile_data = _profile(token_payload['access_token'])
        except (RequestException, ValueError, RuntimeError) as exc:
            error_code = str(exc) if isinstance(exc, ValueError) else 'github_provider_unavailable'
            OAuthFlow.objects.filter(pk=flow.pk).update(
                status=OAuthFlow.Status.FAILED,
                error_code=error_code[:80],
                completed_at=timezone.now(),
            )
            logger.warning('GitHub OAuth failed', extra={'oauth_flow_id': str(flow.id), 'error_code': error_code})
            return HttpResponseRedirect(_frontend_callback(status='error', code=error_code))

        flow.provider_uid = uid
        flow.verified_email = email or ''
        flow.profile_data = profile_data
        if flow.flow == OAuthFlow.Flow.CONNECT:
            return self._complete_connect(request, flow)
        return self._complete_login(request, flow, username)

    def _complete_connect(self, request, flow):
        account = SocialAccount.objects.filter(provider='github', uid=flow.provider_uid).first()
        if account and account.user_id != flow.requested_user_id:
            flow.status = OAuthFlow.Status.FAILED
            flow.error_code = 'github_identity_in_use'
            flow.completed_at = timezone.now()
            flow.save()
            return HttpResponseRedirect(_frontend_callback(status='error', flow='connect', code=flow.error_code))
        if not account:
            SocialAccount.objects.create(
                user=flow.requested_user,
                provider='github',
                uid=flow.provider_uid,
                extra_data=flow.profile_data,
            )
        flow.status = OAuthFlow.Status.COMPLETED
        flow.completed_at = timezone.now()
        flow.save()
        return HttpResponseRedirect(_frontend_callback(status='success', flow='connect', next=flow.return_to))

    def _complete_login(self, request, flow, username):
        social = SocialAccount.objects.select_related('user').filter(provider='github', uid=flow.provider_uid).first()
        if social:
            user = social.user
            if user.status != User.Status.NORMAL or not user.is_active:
                _record_login(request, email=user.email, user=user, reason='candidate_disabled')
                flow.status = OAuthFlow.Status.FAILED
                flow.error_code = 'candidate_disabled'
                flow.completed_at = timezone.now()
                flow.save()
                return HttpResponseRedirect(_frontend_callback(status='error', code=flow.error_code))
            flow.status = OAuthFlow.Status.COMPLETED
            flow.completed_at = timezone.now()
            flow.save()
            _record_login(request, email=user.email, user=user, success=True)
            return _redirect_with_session(request, user, flow, event='github_login')

        if not flow.verified_email:
            flow.status = OAuthFlow.Status.FAILED
            flow.error_code = 'github_verified_email_required'
            flow.completed_at = timezone.now()
            flow.save()
            return HttpResponseRedirect(_frontend_callback(status='error', code=flow.error_code))

        existing = User.objects.filter(email__iexact=flow.verified_email).first()
        if existing:
            raw_link_token = secrets.token_urlsafe(40)
            flow.link_token_hash = _digest(raw_link_token)
            flow.status = OAuthFlow.Status.LINK_REQUIRED
            flow.expires_at = timezone.now() + timedelta(minutes=10)
            flow.save()
            return HttpResponseRedirect(_frontend_callback(
                status='link_required',
                link_token=raw_link_token,
                email_hint=_mask_email(existing.email),
            ))

        with transaction.atomic():
            user = User.objects.create_user(
                username=_unique_username(username, flow.provider_uid),
                email=flow.verified_email,
            )
            SocialAccount.objects.create(
                user=user,
                provider='github',
                uid=flow.provider_uid,
                extra_data=flow.profile_data,
            )
            flow.status = OAuthFlow.Status.COMPLETED
            flow.completed_at = timezone.now()
            flow.save()
        _record_login(request, email=user.email, user=user, success=True)
        return _redirect_with_session(request, user, flow, event='github_register')


class GitHubLinkConfirmView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request):
        enforce_csrf(request)
        raw_token = str(request.data.get('link_token') or '')
        password = str(request.data.get('password') or '')
        with transaction.atomic():
            flow = OAuthFlow.objects.select_for_update().filter(
                link_token_hash=_digest(raw_token),
                status=OAuthFlow.Status.LINK_REQUIRED,
                expires_at__gt=timezone.now(),
            ).first()
            if not flow:
                return Response({'code': 'oauth_link_expired', 'message': '账号绑定确认已过期，请重新授权。'}, status=400)
            user = User.objects.filter(email__iexact=flow.verified_email).first()
            if not user or not user.check_password(password):
                _record_login(request, email=flow.verified_email, user=user, reason='oauth_link_password_invalid')
                return Response({'code': 'oauth_link_password_invalid', 'message': '密码不正确，无法绑定已有账号。'}, status=401)
            if user.status != User.Status.NORMAL or not user.is_active:
                return Response({'code': 'candidate_disabled', 'message': '账号已停用。'}, status=403)
            if SocialAccount.objects.filter(provider='github', uid=flow.provider_uid).exclude(user=user).exists():
                return Response({'code': 'github_identity_in_use', 'message': '该 GitHub 身份已绑定其他账号。'}, status=409)
            SocialAccount.objects.get_or_create(
                user=user,
                provider='github',
                uid=flow.provider_uid,
                defaults={'extra_data': flow.profile_data},
            )
            flow.status = OAuthFlow.Status.COMPLETED
            flow.link_token_hash = ''
            flow.completed_at = timezone.now()
            flow.save()
        _record_login(request, email=user.email, user=user, success=True)
        return _login_response(request, user, event='github_link_login')


class GitHubLogin(APIView):
    """Compatibility endpoint for old clients; new clients must start a server-owned flow."""

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        return Response({
            'code': 'github_oauth_flow_upgraded',
            'message': '请重新发起 GitHub 授权。',
            'start_url': '/api/v1/auth/oauth/github/start/',
        }, status=status.HTTP_409_CONFLICT)


class GitHubConnect(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        return Response({
            'code': 'github_oauth_flow_upgraded',
            'message': '请重新发起 GitHub 绑定授权。',
            'start_url': '/api/v1/auth/oauth/github/start/?flow=connect&return_to=/dashboard/profile',
        }, status=status.HTTP_409_CONFLICT)
