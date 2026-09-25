"""Offline tests only: the HTTP entry point is blocked unless a test supplies a fake."""
import contextlib
import copy
import importlib.util
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('gemini_route_check', ROOT / 'scripts/gemini_route_check.py')
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)
URL = 'https://www.youtube.com/watch?v=gSu2ghFxoiY'
KEY = 'DO-NOT-LOG-this-test-key'


def fixture(spec):
    if 'enum' in spec:
        return spec['enum'][0]
    kind = spec['type']
    if kind == 'object':
        return {k: fixture(v) for k, v in spec['properties'].items()}
    if kind == 'array':
        return [fixture(spec['items']) for _ in range(spec.get('minItems', 0))]
    if kind == 'boolean':
        return False
    return '오프라인 검사 예제'


def response(analysis=None, **extras):
    result = {'candidates': [{'finishReason': 'STOP', 'content': {'parts': [
        {'text': json.dumps(fixture(M.schema()) if analysis is None else analysis, ensure_ascii=False)}
    ]}}]}
    result.update(extras)
    return result


class FakeResponse(io.BytesIO):
    def __init__(self, data):
        super().__init__(json.dumps(data, ensure_ascii=False).encode('utf-8'))
    def getcode(self):
        return 200


class RouteCheckTests(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(M, 'OPEN', side_effect=AssertionError('Real HTTP is forbidden in offline tests'))
        self.open = patcher.start()
        self.addCleanup(patcher.stop)

    def success(self, data=None):
        self.open.side_effect = None
        self.open.return_value = FakeResponse(response() if data is None else data)
        return M.run_check(URL, live=True, api_key=KEY)

    def test_same_model_prompt_schema_and_video(self):
        payload = M.request_payload(URL)
        self.assertIn(M.DEFAULT_MODEL + ':generateContent', M.ENDPOINT)
        self.assertEqual(payload['contents'][0]['parts'], [
            {'text': M.PROMPT}, {'fileData': {'fileUri': URL}}
        ])
        self.assertEqual(payload['generationConfig'], {
            'responseFormat': {'text': {'mimeType': 'application/json', 'schema': M.schema()}}
        })
        self.assertEqual(set(payload), {'contents', 'generationConfig'})
        for key in ('expected', 'expected_label', 'comparison', 'safetySettings', 'tools'):
            self.assertNotIn(key, payload)
        self.open.assert_not_called()

    def test_default_dry_run_never_connects(self):
        report = M.run_check(URL, api_key=KEY)
        self.assertEqual((report['status'], report['attempts']), ('prepared', 0))
        self.assertIsNone(report['analysis'])
        self.open.assert_not_called()

    def test_missing_key_never_connects(self):
        report = M.run_check(URL, live=True)
        self.assertEqual(report['errorCode'], 'missing_api_key')
        self.assertEqual(report['attempts'], 0)
        self.open.assert_not_called()

    def test_invalid_url_never_connects(self):
        with self.assertRaises(M.LabError):
            M.run_check('https://evil.invalid/watch?v=gSu2ghFxoiY', live=True, api_key=KEY)
        self.open.assert_not_called()

    def test_success_is_exactly_one_post(self):
        report = self.success()
        self.assertEqual(report['status'], 'success')
        self.assertTrue(report['schemaValid'])
        self.assertEqual(report['attempts'], 1)
        self.open.assert_called_once()
        req = self.open.call_args.args[0]
        self.assertEqual(req.get_method(), 'POST')
        self.assertEqual(req.full_url, M.ENDPOINT)
        self.assertNotIn(KEY, req.full_url)
        self.assertNotIn(KEY, req.data.decode())
        self.assertEqual(req.get_header('X-goog-api-key'), KEY)
        self.assertEqual(self.open.call_args.kwargs['timeout'], 240)

    def test_503_no_retry_no_message_leak(self):
        body = io.BytesIO(json.dumps({'error': {'code': 'service_unavailable', 'message': KEY}}).encode())
        self.open.side_effect = M.HTTPError('https://example.invalid/' + KEY, 503, KEY,
                                           {'Retry-After': '30'}, body)
        report = M.run_check(URL, live=True, api_key=KEY)
        self.assertEqual(report['status'], 'failed')
        self.assertEqual(report['httpStatus'], 503)
        self.assertEqual(report['errorCode'], 'service_unavailable')
        self.assertEqual(report['retryAfterSeconds'], 30)
        self.open.assert_called_once()
        self.assertNotIn(KEY, json.dumps(report))

    def test_all_http_errors_single_attempt(self):
        for http in (400, 401, 402, 403, 404, 429, 500, 502, 503, 504):
            with self.subTest(http=http):
                self.open.reset_mock()
                self.open.side_effect = M.HTTPError('https://example.invalid', http, KEY, {},
                    io.BytesIO(json.dumps({'error': {'code': http, 'status': 'RESOURCE_EXHAUSTED', 'message': KEY}}).encode()))
                report = M.run_check(URL, live=True, api_key=KEY)
                self.open.assert_called_once()
                self.assertEqual(report['attempts'], 1)
                self.assertEqual(report['status'], 'failed')
                self.assertNotIn(KEY, json.dumps(report))

    def test_daily_quota_single_attempt(self):
        self.open.side_effect = M.HTTPError('https://example.invalid', 429, 'error', {},
            io.BytesIO(b'{"error":{"code":"quota_exceeded"}}'))
        report = M.run_check(URL, live=True, api_key=KEY)
        self.assertEqual(report['errorCode'], 'quota_exceeded')
        self.open.assert_called_once()

    def test_unrecognized_error_body_is_not_recorded(self):
        for raw in (b'<html>private</html>', json.dumps({'error': {'code': KEY, 'message': KEY}}).encode(), b'[]'):
            with self.subTest(raw=raw):
                self.open.side_effect = M.HTTPError('https://example.invalid', 503, 'error',
                                                   {'Retry-After': KEY}, io.BytesIO(raw))
                report = M.run_check(URL, live=True, api_key=KEY)
                self.assertEqual(report['errorCode'], 'unknown_http_error')
                self.assertIsNone(report['retryAfterSeconds'])
                self.assertNotIn(KEY, json.dumps(report))

    def test_timeout_single_attempt(self):
        self.open.side_effect = TimeoutError(KEY)
        report = M.run_check(URL, live=True, api_key=KEY)
        self.assertEqual(report['errorCode'], 'network_error')
        self.assertEqual(report['attempts'], 1)
        self.open.assert_called_once()
        self.assertNotIn(KEY, json.dumps(report))

    def test_redirect_is_never_followed(self):
        self.assertIsNone(M.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://evil.invalid'))
        self.open.assert_not_called()

    def test_thoughts_are_not_parsed_or_reported(self):
        data = response()
        data['candidates'][0]['content']['parts'].insert(0, {'thought': True, 'text': KEY})
        report = self.success(data)
        self.assertEqual(report['status'], 'success')
        self.assertNotIn(KEY, json.dumps(report))

    def test_blocked_and_truncated_outputs_are_not_success(self):
        for finish in ('MAX_TOKENS', 'SAFETY', 'RECITATION', None):
            with self.subTest(finish=finish):
                data = response()
                data['candidates'][0]['finishReason'] = finish
                report = self.success(data)
                self.assertEqual(report['errorCode'], 'generation_not_completed')
                self.assertIsNone(report['analysis'])
        report = self.success(response(promptFeedback={'blockReason': 'SAFETY'}))
        self.assertEqual(report['errorCode'], 'generation_blocked')

    def test_non_json_and_invalid_envelopes_not_success(self):
        for data in ([], {}, {'candidates': [None]}):
            self.assertEqual(self.success(data)['status'], 'failed')
        data = response()
        data['candidates'][0]['content']['parts'] = [{'text': 'not JSON'}]
        self.assertEqual(self.success(data)['errorCode'], 'invalid_analysis_json')

    def test_missing_field_wrong_type_enum_and_extra_field(self):
        good = fixture(M.schema())
        variants = []
        missing = copy.deepcopy(good)
        del missing['visual_dependency']
        variants.append(missing)
        for key, val in (('setup_clear', 'true'), ('context_required', 1),
                         ('story_pattern', 'invalid'), ('why', []), ('unexpected', 'field')):
            item = copy.deepcopy(good)
            item[key] = val
            variants.append(item)
        for item in variants:
            self.assertEqual(self.success(response(item))['errorCode'], 'invalid_analysis_schema')

    def test_usage_missing_is_not_zero_and_counts_not_double_counted(self):
        report = self.success()
        self.assertIsNone(report['usage'])
        self.assertIsNone(report['billingEstimateUsd'])
        report = self.success(response(usageMetadata={
            'promptTokenCount': 100, 'candidatesTokenCount': 20, 'thoughtsTokenCount': 30,
            'totalTokenCount': 150, 'extra': KEY, 'cachedContentTokenCount': -1,
        }))
        self.assertEqual(report['usage'], {'promptTokenCount': 100, 'candidatesTokenCount': 20,
                                          'thoughtsTokenCount': 30, 'totalTokenCount': 150})
        self.assertNotIn(KEY, json.dumps(report))

    def test_fingerprints_do_not_depend_on_key_or_url_format(self):
        a = M.run_check(URL)
        b = M.run_check('https://youtu.be/gSu2ghFxoiY', api_key=KEY)
        self.assertEqual(a['promptSha256'], b['promptSha256'])
        self.assertEqual(a['schemaSha256'], b['schemaSha256'])
        self.assertEqual(a['videoUrl'], b['videoUrl'])
        self.open.assert_not_called()

    def test_dry_run_main_writes_only_local_reports(self):
        with tempfile.TemporaryDirectory() as td, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(M.main(['--youtube-url', URL, '--out', td]), 0)
            self.assertEqual(sorted(p.name for p in Path(td).iterdir()), ['gemini-route-check.json', 'gemini-route-check.md'])
            report = json.loads((Path(td) / 'gemini-route-check.json').read_text())
            self.assertEqual(report['attempts'], 0)
        self.open.assert_not_called()

    def test_live_failure_still_writes_safe_report_and_nonzero_exit(self):
        self.open.side_effect = M.HTTPError('https://example.invalid/' + KEY, 503, KEY, {}, io.BytesIO(b'{}'))
        with tempfile.TemporaryDirectory() as td, mock.patch.dict(os.environ, {'GEMINI_API_KEY': KEY}), \
                contextlib.redirect_stdout(io.StringIO()) as logs:
            self.assertEqual(M.main(['--youtube-url', URL, '--live', '--out', td]), 2)
            text = ''.join(p.read_text() for p in Path(td).iterdir())
            self.assertIn('failed', text)
            self.assertNotIn(KEY, text + logs.getvalue())
        self.open.assert_called_once()

    def test_workflow_is_manual_and_defaults_offline(self):
        text = (ROOT / '.github/workflows/gemini-route-check.yml').read_text()
        self.assertIn('workflow_dispatch:', text)
        self.assertNotIn('schedule:', text)
        self.assertNotIn('push:', text)
        self.assertIn('default: false', text)
        self.assertIn('if: always()', text)
        self.assertIn('--youtube-url "$YOUTUBE_URL"', text)
        self.assertIn('contents: read', text)


if __name__ == '__main__':
    unittest.main()
