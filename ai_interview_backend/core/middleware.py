import uuid


class RequestIdMiddleware:
    header_name = 'HTTP_X_REQUEST_ID'

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        incoming = str(request.META.get(self.header_name, '') or '').strip()
        request.request_id = incoming[:64] if incoming else uuid.uuid4().hex
        response = self.get_response(request)
        response['X-Request-Id'] = request.request_id
        return response
