import hashlib

from rest_framework.response import Response

from .broker_dlq import DLQValidationError, inspect_queue, queue_target, replay_batch
from .idempotency import run_staff_idempotent
from .operations_views import operation_reason
from .views import StaffProtectedView, audit
from .models import AdminAuditEvent


class BrokerDLQAdminView(StaffProtectedView):
    required_permissions = ['platform_events.view']

    def get(self, request):
        name = request.query_params.get('queue', '')
        try:
            return Response(inspect_queue(name))
        except DLQValidationError as exc:
            return Response({'code': str(exc)}, status=400)
        except Exception:
            return Response({'code': 'broker_unavailable', 'retryable': True}, status=503)

    def post(self, request):
        if not ({'platform_events.replay', '*'} & request.user.permission_set()):
            return Response({'code': 'permission_denied'}, status=403)
        reason, error = operation_reason(request)
        if error:
            return error
        name = request.data.get('queue', '')
        limit = request.data.get('limit', 10)
        dry_run = request.data.get('dry_run', True)
        try:
            if not isinstance(name, str):
                raise DLQValidationError('invalid_dlq_queue')
            queue_target(name)
            if type(limit) is not int or not 1 <= limit <= 100 or type(dry_run) is not bool:
                raise DLQValidationError('invalid_replay_options')
        except DLQValidationError as exc:
            return Response({'code': str(exc)}, status=400)

        def apply():
            before = {'queue': name, 'limit': limit, 'dry_run': dry_run}
            # Never let an expired request claim silently consume the NEXT
            # batch after a process crash or loss of the final DB receipt.
            # Store only a hash, not the caller's idempotency key.
            key_hash = hashlib.sha256(str(request.headers.get('Idempotency-Key')).encode()).hexdigest()
            prior = AdminAuditEvent.objects.filter(
                actor=request.user, action='broker_dlq.replay_started',
                resource_id=name, metadata__idempotency_key_hash=key_hash,
            ).exists()
            if prior:
                return Response({'code': 'broker_replay_outcome_uncertain',
                                 'message': '该批次已有开始记录但响应未完成，请先核对审计与队列，再以新操作发起下一批。',
                                 'queue': name}, status=409)
            audit(request, action='broker_dlq.replay_started', resource_type='RabbitMQQueue',
                  resource_id=name, reason=reason, before=before,
                  metadata={'idempotency_key_hash': key_hash})

            def receipt(summary):
                audit(request, action='broker_dlq.publish_confirmed', resource_type='RabbitMQQueue',
                      resource_id=name, reason=reason, before=before, after=summary)

            try:
                result = replay_batch(name, limit=limit, dry_run=dry_run, record_confirm=receipt)
            except Exception:
                # Do not expose connection errors/credentials or private messages.
                result = {'queue': name, 'code': 'broker_unavailable', 'retryable': True}
                audit(request, action='broker_dlq.replay_failed', resource_type='RabbitMQQueue',
                      resource_id=name, reason=reason, before=before, after=result)
                return Response(result, status=503)
            audit(request, action='broker_dlq.replay_finished', resource_type='RabbitMQQueue',
                  resource_id=name, reason=reason, before=before, after=result)
            # A partial batch is a final receipt, not an automatic retry: some
            # messages may already have been confirmed. New action = new key.
            return Response(result)

        return run_staff_idempotent(request, f'broker-dlq.{name}', apply)
