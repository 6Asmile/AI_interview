from rest_framework.views import exception_handler as drf_exception_handler


def _field_errors(data):
    if not isinstance(data, dict):
        return {}
    return {
        key: value
        for key, value in data.items()
        if key not in {'detail', 'error', 'message', 'code', 'retryable'}
    }


def api_exception_handler(exc, context):
    response = drf_exception_handler(exc, context)
    if response is None:
        return None
    request = context.get('request')
    data = response.data
    if isinstance(data, dict):
        message = data.get('detail') or data.get('error') or data.get('message')
        code = data.get('code') or getattr(exc, 'default_code', 'request_failed')
        retryable = bool(data.get('retryable', response.status_code >= 500))
    else:
        message = data
        code = getattr(exc, 'default_code', 'request_failed')
        retryable = response.status_code >= 500
    if isinstance(message, (list, dict)):
        message = '请求参数不符合要求。'
    response.data = {
        'code': str(code),
        'message': str(message or '请求处理失败。'),
        'field_errors': _field_errors(data),
        'request_id': getattr(request, 'request_id', ''),
        'retryable': retryable,
    }
    return response
