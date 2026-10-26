import importlib.util
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
import urllib.error
import sys

spec = importlib.util.spec_from_file_location('deterministic_evaluation', Path(__file__).resolve().parents[1] / 'run_deterministic_evaluation.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class EvaluationReportTests(unittest.TestCase):
    def test_owned_asgi_cleanup_targets_only_its_process_tree(self):
        scripts = Path(__file__).resolve().parents[1]
        with patch.object(sys, 'path', [str(scripts), *sys.path]):
            spec = importlib.util.spec_from_file_location('auth_http_evaluation', scripts / 'authenticated_http_evaluation.py')
            auth = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(auth)
        process = Mock(pid=43210)
        process.poll.return_value = None
        with patch.object(auth.subprocess, 'Popen', return_value=process) as spawn, patch.object(
            auth.subprocess, 'run'
        ) as stop, patch.object(auth.socket, 'create_connection') as ready:
            ready.return_value.__enter__ = Mock()
            ready.return_value.__exit__ = Mock(return_value=False)
            with self.assertRaisesRegex(RuntimeError, 'synthetic_test_exit'):
                with auth.owned_asgi_server(pooled=True) as url:
                    self.assertTrue(url.startswith('http://127.0.0.1:'))
                    raise RuntimeError('synthetic_test_exit')
        self.assertEqual(spawn.call_args.kwargs['env']['POSTGRES_POOL_ENABLED'], 'true')
        if auth.os.name == 'nt':
            self.assertEqual(stop.call_args.args[0], ['taskkill', '/PID', '43210', '/T', '/F'])
        else:
            process.terminate.assert_called_once()
        process.wait.assert_called_once()

    def test_authenticated_client_reuses_tls_context_and_thread_opener(self):
        spec = importlib.util.spec_from_file_location('http_evaluation', Path(__file__).resolve().parents[1] / 'http_qps_evaluation.py')
        http = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(http)
        response = Mock(status=200)
        response.read.return_value = b'{}'
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        opener = Mock()
        opener.open.return_value = response
        with patch.object(http.ssl, 'create_default_context') as context, patch.object(
            http.urllib.request, 'build_opener', return_value=opener
        ) as build:
            result = http.evaluate('http://127.0.0.1', .3, 1, 1, identities=[{'Authorization': 'synthetic'}], arrival_rate=10)
        self.assertEqual(result['request_count'], 3)
        context.assert_called_once()
        build.assert_called_once()
        self.assertEqual(opener.open.call_count, 3)
        self.assertIsNotNone(result['schedule_lag_ms']['p95'])

    def test_fixed_arrival_write_cap_and_measurement_label(self):
        spec = importlib.util.spec_from_file_location('http_evaluation', Path(__file__).resolve().parents[1] / 'http_qps_evaluation.py')
        http = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(http)
        response = Mock(status=201)
        response.read.return_value = b'{}'
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        with patch.object(http.urllib.request, 'urlopen', return_value=response):
            result = http.evaluate('http://test', 1, 2, 1, arrival_rate=10, max_requests=2, method='POST')
        self.assertEqual(result['scheduled_requests'], 2)
        self.assertEqual(result['request_count'] + result['client_backpressure_drops'], 2)
        self.assertEqual(result['evidence_level'], 'real_http_local_write_endpoint')
        self.assertEqual(result['load_model'], 'fixed_arrival')
        self.assertEqual(result['offered_success_rate'], result['successful_requests'] / 2)

    def test_http_200_with_wrong_business_payload_is_not_success(self):
        spec = importlib.util.spec_from_file_location('http_evaluation', Path(__file__).resolve().parents[1] / 'http_qps_evaluation.py')
        http = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(http)
        clock = iter([0, 0, 2])
        response = Mock(status=200)
        response.read.return_value = b'{}'
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        with patch.object(http.time, 'monotonic', side_effect=lambda: next(clock)), patch.object(
            http.urllib.request, 'urlopen', return_value=response
        ):
            result = http.evaluate('http://test', 1, 1, 1, response_validator=lambda _index, _body: False)
        self.assertEqual(result['http_status_counts'], {'200': 1})
        self.assertEqual(result['invalid_response_count'], 1)
        self.assertEqual(result['successful_requests'], 0)
        self.assertEqual(result['status'], 'failed')

    def test_authenticated_load_rejects_nonlocal_token_destination(self):
        spec = importlib.util.spec_from_file_location('http_evaluation', Path(__file__).resolve().parents[1] / 'http_qps_evaluation.py')
        http = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(http)
        with self.assertRaisesRegex(ValueError, 'loopback'):
            http.evaluate('https://example.com', 1, 1, 1, identities=[{'Authorization': 'Bearer synthetic'}])
        self.assertIsNone(http.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://example.com'))

    def test_http_timeout_is_separate_from_transport_error(self):
        spec = importlib.util.spec_from_file_location('http_evaluation', Path(__file__).resolve().parents[1] / 'http_qps_evaluation.py')
        http = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(http)
        clock = iter([0, 0, 2])
        with patch.object(http.time, 'monotonic', side_effect=lambda: next(clock)), patch.object(
            http.urllib.request, 'urlopen', side_effect=urllib.error.URLError(TimeoutError())
        ):
            result = http.evaluate('http://test', 1, 1, 1)
        self.assertEqual(result['timeout_rate'], 1)
        self.assertEqual(result['transport_error_rate'], 0)
        self.assertEqual(result['status'], 'failed')

    def test_http_throttling_is_not_automatically_correct(self):
        spec = importlib.util.spec_from_file_location('http_evaluation', Path(__file__).resolve().parents[1] / 'http_qps_evaluation.py')
        http = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(http)
        clock = iter([0, 0, 2])
        with patch.object(http.time, 'monotonic', side_effect=lambda: next(clock)), patch.object(
            http.urllib.request, 'urlopen', side_effect=urllib.error.HTTPError('http://test', 429, 'limited', {}, None)
        ):
            result = http.evaluate('http://test', 1, 1, 1)
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(result['success_rate'], 0)
        self.assertEqual(result['rate_limited_rate'], 1)
        self.assertEqual(result['throttle_correctness'], 'pending-verification')

    def test_redirect_is_not_successful_business_response(self):
        spec = importlib.util.spec_from_file_location('http_evaluation', Path(__file__).resolve().parents[1] / 'http_qps_evaluation.py')
        http = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(http)
        clock = iter([0, 0, 2])
        with patch.object(http.time, 'monotonic', side_effect=lambda: next(clock)), patch.object(
            http.urllib.request, 'urlopen', side_effect=urllib.error.HTTPError('http://test', 302, 'redirect', {}, None)
        ):
            result = http.evaluate('http://test', 1, 1, 1)
        self.assertEqual(result['successful_requests'], 0)
        self.assertEqual(result['status'], 'failed')

    def test_nearest_rank_and_empty(self):
        self.assertIsNone(module.percentile([], .95))
        self.assertEqual(module.percentile(range(1, 21), .95), 19)

    def test_skips_are_not_successes(self):
        result = module.summarize([{'status': 'passed'}, {'status': 'skipped'}])
        self.assertEqual(result['executed'], 1)
        self.assertEqual(result['status'], 'partial')

    def test_empty_is_not_a_pass_rate(self):
        self.assertIsNone(module.summarize([])['pass_rate'])

    def test_failure_is_failure(self):
        self.assertEqual(module.summarize([{'status': 'error'}])['status'], 'failed')

    def test_container_cleanup_rejects_foreign_owner(self):
        spec = importlib.util.spec_from_file_location('real_infrastructure', Path(__file__).resolve().parents[1] / 'real_infrastructure_evaluation.py')
        infra_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(infra_module)
        infra = infra_module.Infrastructure()
        infra.owned = [infra.prefix + '-redis']
        infra.docker = Mock(return_value='foreign-owner')
        with self.assertRaisesRegex(RuntimeError, 'ownership'):
            infra.close()
        self.assertEqual(infra.docker.call_count, 1)

    def test_empty_run_is_partial(self):
        self.assertEqual(module.summarize([])['status'], 'partial')
