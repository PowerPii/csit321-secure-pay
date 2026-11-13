from apps.common.ids import new_id

REQUEST_ID_HEADER = "SecurePay-Request-Id"


class RequestIdMiddleware:
    """Give every request a `req_...` correlation ID (API-CONTRACT.md section 2, FR-TXN-16).

    It is sent back in the `SecurePay-Request-Id` header, put into error bodies and stored
    on audit events. A client-supplied ID is never trusted.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.request_id = new_id("req")
        response = self.get_response(request)
        response[REQUEST_ID_HEADER] = request.request_id
        return response
