"""CLI browser harness: captures/redacts CLI code, never logs fixture credentials."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import datetime as dt

ROOT = Path(__file__).resolve().parents[1]


def _run_once(resume_only=False):
    directory = ROOT / 'output/playwright'
    directory.mkdir(parents=True, exist_ok=True)
    fixture_file = directory / 'live-fixture.json'
    code_file = directory / 'live-browser-code.js'
    result_file = directory / 'live-browser-result.json'
    config = directory / 'concurrent-media.config.json'
    if not config.exists():
        config.write_text(json.dumps({'browser': {'browserName': 'chromium', 'launchOptions': {'args': ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream']}, 'contextOptions': {'permissions': ['camera', 'microphone'], 'viewport': {'width': 1440, 'height': 1000}}}}), encoding='utf-8')
    result = {'status': 'failed', 'rows': [], 'scope': 'real_browser_resume_only_no_ai' if resume_only else 'real_browser_fake_media_no_ai'}
    try:
        env = {**os.environ, 'PYTHONUTF8': '1'}
        prepare_command = [sys.executable, 'manage.py', 'prepare_browser_evaluation', '--output', str(fixture_file)]
        if resume_only:
            prepare_command.append('--resume-only')
        prepare = subprocess.run(prepare_command,
            cwd=ROOT / 'ai_interview_backend', env=env, capture_output=True, timeout=30)
        if prepare.returncode:
            raise RuntimeError('fixture_creation_failed')
        fixture = json.loads(fixture_file.read_text(encoding='utf-8'))
        code_file.write_text((ROOT / 'scripts/browser_evaluation.js').read_text(encoding='utf-8').replace('__FIXTURE__', json.dumps(fixture)), encoding='utf-8')
        bash = r'C:\Program Files\Git\bin\bash.exe'
        wrapper = '/c/Users/26465/.codex/skills/playwright/scripts/playwright_cli.sh'
        def cli(arguments, timeout=90):
            command = f'npm_config_offline=true bash {wrapper} -s=ifaceoff-real-evaluation {arguments}'
            return subprocess.run([bash, '-lc', command], cwd=ROOT, capture_output=True, text=True, encoding='utf-8', timeout=timeout)
        opened = cli('open http://127.0.0.1:5173/login --browser=chrome --config=output/playwright/concurrent-media.config.json')
        if opened.returncode:
            raise RuntimeError('browser_open_failed')
        cli('snapshot')
        executed = cli('run-code --filename=output/playwright/live-browser-code.js', timeout=240)
        match = re.search(r'### Result\s*\n(.*?)\n###', executed.stdout, re.S)
        if not match:
            # Preserve only the CLI error, never its echoed function containing credentials.
            result['error'] = executed.stdout.split('### Error')[-1].split('###')[0].strip()[:500] if '### Error' in executed.stdout else 'browser_result_missing'
        else:
            result.update(json.loads(match.group(1)))
            result['status'] = 'failed' if any(row['status'] == 'failed' for row in result['rows']) else 'partial'
        cli('close')
    except Exception as error:
        result['error_type'] = type(error).__name__
    finally:
        for path in (fixture_file, code_file):
            if path.exists():
                path.unlink()  # exact private generated artifacts, not source/user files
    result_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    if result.get('user_id'):
        verified = subprocess.run([sys.executable, 'manage.py', 'verify_browser_evaluation', '--result', str(result_file)],
            cwd=ROOT / 'ai_interview_backend', env={**os.environ, 'PYTHONUTF8': '1'}, capture_output=True, timeout=90)
        result = json.loads(result_file.read_text(encoding='utf-8'))
        if verified.returncode:
            result.update(status='failed', verification_error='database_or_media_verification_failed')
            result_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(str(result_file))
    archive = directory / ('browser-' + dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S-%fZ') + '.json')
    archive.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return 1 if result['status'] == 'failed' else 0


def run(resume_only=False, repeat=1):
    import math
    runs = []
    failed = False
    for _ in range(repeat):
        failed = bool(_run_once(resume_only)) or failed
        runs.append(json.loads((ROOT / 'output/playwright/live-browser-result.json').read_text(encoding='utf-8')))
    measurements = {}
    for result in runs:
        for row in result['rows']:
            if row['status'] == 'passed':
                for key in ('final_edit_to_saved_indicator_ms', 'final_edit_to_preview_ms', 'click_to_download_ms'):
                    if key in row:
                        measurements.setdefault(row['name'], []).append(row[key])
    rows = [row for result in runs for row in result['rows']]
    summary = {'status': 'failed' if failed else 'partial', 'runs': runs,
               'summary': {'total': len(rows), 'passed': sum(row['status'] == 'passed' for row in rows),
                           'failed': sum(row['status'] == 'failed' for row in rows)},
               'limitations': ['合成小简历、本地服务；低样本分位数不证明生产 SLO 或全部模板通过。'],
               'measurements': {name: {'sample_count': len(values),
                   **{label: sorted(values)[math.ceil(len(values) * q) - 1] for label, q in (('p50_ms', .5), ('p95_ms', .95), ('p99_ms', .99))}}
                   for name, values in measurements.items()}}
    target = ROOT / 'output/playwright/browser-evaluation-summary.json'
    target.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(str(target))
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(run())
