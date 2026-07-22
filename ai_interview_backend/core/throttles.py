from rest_framework.throttling import AnonRateThrottle, UserRateThrottle


class LoginRateThrottle(AnonRateThrottle):
    scope = 'login'

    def get_cache_key(self, request, view):
        ident = self.get_ident(request)
        email = str(request.data.get('email') or '').strip().lower()[:160]
        return self.cache_format % {'scope': self.scope, 'ident': f'{ident}:{email}'}


class VerificationRateThrottle(AnonRateThrottle):
    scope = 'verification'


class ChatRateThrottle(UserRateThrottle):
    scope = 'chat'


class UploadRateThrottle(UserRateThrottle):
    scope = 'upload'


class AIActionRateThrottle(UserRateThrottle):
    scope = 'ai_action'
