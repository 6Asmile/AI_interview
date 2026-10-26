import re
import uuid
from contextvars import ContextVar


_current_request_id = ContextVar('ifaceoff_request_id', default='')
_current_correlation_id = ContextVar('ifaceoff_correlation_id', default='')
_current_trace_id = ContextVar('ifaceoff_trace_id', default='')
_SAFE_ID = re.compile(r'^[A-Za-z0-9._:-]{1,64}$')


def get_current_request_id() -> str:
    return _current_request_id.get()


def get_current_correlation_id() -> str:
    return _current_correlation_id.get()


def get_current_trace_id() -> str:
    return _current_trace_id.get()


def _safe_request_id(raw: object) -> str:
    value = str(raw or '').strip()
    return value if _SAFE_ID.fullmatch(value) else uuid.uuid4().hex


def _correlation_id(raw: object) -> str:
    try:
        return str(uuid.UUID(str(raw or '').strip()))
    except (TypeError, ValueError, AttributeError):
        return str(uuid.uuid4())


def _trace_id(raw: object) -> str:
    value = str(raw or '').strip()
    return value if _SAFE_ID.fullmatch(value) else uuid.uuid4().hex


class RequestIdMiddleware:
    header_name = 'HTTP_X_REQUEST_ID'

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.request_id = _safe_request_id(request.META.get(self.header_name))
        request.correlation_id = _correlation_id(request.META.get('HTTP_X_CORRELATION_ID'))
        request.trace_id = _trace_id(request.META.get('HTTP_X_TRACE_ID'))
        request_token = _current_request_id.set(request.request_id)
        correlation_token = _current_correlation_id.set(request.correlation_id)
        trace_token = _current_trace_id.set(request.trace_id)
        try:
            response = self.get_response(request)
            response['X-Request-Id'] = request.request_id
            response['X-Correlation-Id'] = request.correlation_id
            response['X-Trace-Id'] = request.trace_id
            return response
        finally:
            _current_trace_id.reset(trace_token)
            _current_correlation_id.reset(correlation_token)
            _current_request_id.reset(request_token)
