import http from 'k6/http';
import exec from 'k6/execution';
import { check } from 'k6';

const baseUrl = (__ENV.BASE_URL || 'http://127.0.0.1:8000/api/v1').replace(/\/$/, '');
const answerText = __ENV.ANSWER_TEXT || '';
const accessToken = __ENV.ACCESS_TOKEN || '';
const sessionCookie = __ENV.SESSION_COOKIE || '';

function loadCases() {
  if (__ENV.AGENT_CASES_FILE) {
    return JSON.parse(open(__ENV.AGENT_CASES_FILE));
  }
  if (__ENV.SESSION_ID && __ENV.QUESTION_ID) {
    return [{ session_id: __ENV.SESSION_ID, question_id: Number(__ENV.QUESTION_ID) }];
  }
  throw new Error('Set AGENT_CASES_FILE or both SESSION_ID and QUESTION_ID.');
}

const cases = loadCases();
http.setResponseCallback(http.expectedStatuses({ min: 200, max: 399 }, 409));

const scenarios = {
  agent_acceptance: {
    executor: 'per-vu-iterations',
    exec: 'submitAnswer',
    vus: Number(__ENV.AGENT_VUS || 100),
    iterations: 1,
    maxDuration: '2m',
  },
  resume_state_reads: {
    executor: 'per-vu-iterations',
    exec: 'readResumeState',
    vus: Number(__ENV.RESUME_VUS || 500),
    iterations: 1,
    startTime: '3s',
    maxDuration: '2m',
  },
};

if (__ENV.EVENTS_URL) {
  scenarios.event_stream_reconnects = {
    executor: 'per-vu-iterations',
    exec: 'readEventStream',
    vus: Number(__ENV.EVENT_VUS || 500),
    iterations: 1,
    startTime: '6s',
    maxDuration: '2m',
  };
}

export const options = {
  scenarios,
  thresholds: {
    'http_req_duration{scenario:agent_acceptance}': ['p(95)<300'],
    'http_req_duration{scenario:resume_state_reads}': ['p(95)<500'],
    http_req_failed: ['rate<0.01'],
  },
};

function headers(extra = {}) {
  const result = {
    Accept: 'application/json',
    ...extra,
  };
  if (accessToken) result.Authorization = `Bearer ${accessToken}`;
  if (sessionCookie) result.Cookie = sessionCookie;
  return result;
}

function caseForVu() {
  return cases[(exec.vu.idInTest - 1) % cases.length];
}

export function submitAnswer() {
  if (!answerText) throw new Error('Set ANSWER_TEXT to a real test answer.');
  const item = caseForVu();
  const idempotencyKey = cases.length === 1
    ? (__ENV.IDEMPOTENCY_KEY || `load-duplicate-${item.session_id}-${item.question_id}`)
    : `load-${__ENV.RUN_TAG || Date.now()}-${item.session_id}-${item.question_id}`;
  const response = http.post(
    `${baseUrl}/interviews/${item.session_id}/submit-answer-stream/?async=true`,
    JSON.stringify({ question_id: item.question_id, answer_text: answerText }),
    {
      headers: headers({
        'Content-Type': 'application/json',
        Prefer: 'respond-async',
        'Idempotency-Key': idempotencyKey,
      }),
      tags: { operation: 'agent_acceptance' },
    },
  );
  check(response, {
    'answer accepted, replayed, or briefly busy': (r) => r.status === 202 || r.status === 409,
    'no server error': (r) => r.status < 500,
  });
}

export function readResumeState() {
  const item = caseForVu();
  const response = http.get(
    `${baseUrl}/interviews/${item.session_id}/resume-state/`,
    { headers: headers(), tags: { operation: 'resume_state' } },
  );
  check(response, {
    'resume state available': (r) => r.status === 200,
    'resume action present': (r) => {
      if (r.status !== 200) return false;
      const body = r.json();
      return ['continue', 'wait', 'retry_generation', 'finish'].includes(body.resume_action);
    },
  });
}

export function readEventStream() {
  const configured = __ENV.EVENTS_URL;
  const url = configured.startsWith('http') ? configured : `${baseUrl}${configured}`;
  const separator = url.includes('?') ? '&' : '?';
  const response = http.get(`${url}${separator}follow=true`, {
    headers: headers({ 'Last-Event-ID': __ENV.LAST_EVENT_ID || '0-0' }),
    responseType: 'none',
    timeout: '40s',
    tags: { operation: 'event_stream_reconnect' },
  });
  check(response, { 'event stream connected': (r) => r.status === 200 });
}
