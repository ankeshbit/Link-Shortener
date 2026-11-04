import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  stages: [
    { duration: '10s', target: 50 },  // Ramp-up to 50 users over 10s
    { duration: '20s', target: 100 }, // Ramp-up & sustain 100 users over 20s
    { duration: '5s', target: 0 },    // Ramp-down to 0 users over 5s
  ],
  thresholds: {
    http_req_failed: ['rate<0.05'], // < 5% failure rate
    http_req_duration: ['p(95)<1500'], // Baseline SLO threshold (< 1500ms)
  },
};

const BASE_URL = __ENV.BASE_URL || 'http://127.0.0.1:8000';

export function setup() {
  console.log(`[setup] Starting test setup against ${BASE_URL}...`);

  // 1. Register or login a dedicated test user
  const email = `k6_bench_${Date.now()}_${Math.floor(Math.random() * 100000)}@bytelink.co`;
  const password = 'SuperSecurePassword123!';

  const regRes = http.post(
    `${BASE_URL}/api/auth/register`,
    JSON.stringify({ email, password }),
    { headers: { 'Content-Type': 'application/json' } }
  );

  let token = null;
  if (regRes.status === 201) {
    token = regRes.json('access_token');
  } else {
    const logRes = http.post(
      `${BASE_URL}/api/auth/login`,
      JSON.stringify({ email, password }),
      { headers: { 'Content-Type': 'application/json' } }
    );
    token = logRes.json('access_token');
  }

  if (!token) {
    throw new Error(`[setup] Authentication failed: status ${regRes.status} body: ${regRes.body}`);
  }

  console.log(`[setup] Authenticated successfully. Generating ~1,000 links in batches...`);

  const shortIds = [];
  const totalLinks = 1000;
  const batchSize = 50;
  const authHeaders = {
    'Content-Type': 'application/json',
    Authorization: `Bearer ${token}`,
  };

  const timestamp = Date.now();

  for (let b = 0; b < totalLinks; b += batchSize) {
    const batchRequests = [];
    for (let i = b; i < b + batchSize && i < totalLinks; i++) {
      const alias = `bench_${timestamp}_${i}`;
      batchRequests.push([
        'POST',
        `${BASE_URL}/api/shorten`,
        JSON.stringify({
          target_url: `https://example.com/target-${i}`,
          custom_alias: alias,
        }),
        { headers: authHeaders },
      ]);
    }

    const responses = http.batch(batchRequests);
    for (let j = 0; j < responses.length; j++) {
      const res = responses[j];
      if (res.status === 200) {
        const payload = res.json();
        shortIds.push(payload.short_id);
      }
    }
  }

  console.log(`[setup] Successfully created ${shortIds.length} short links for load testing.`);
  return { shortIds };
}

export default function (data) {
  if (!data || !data.shortIds || data.shortIds.length === 0) {
    return;
  }

  const shortId = data.shortIds[Math.floor(Math.random() * data.shortIds.length)];
  const url = `${BASE_URL}/${shortId}`;

  // Hammer GET /{short_id} without following redirects
  const res = http.get(url, { redirects: 0 });

  check(res, {
    'status is redirect (301, 302, 303, 307)': (r) =>
      [301, 302, 303, 307].indexOf(r.status) !== -1,
  });

  // Short pause to control pacing
  sleep(0.005);
}

export function teardown(data) {
  console.log(`[teardown] Fetching final metrics from ${BASE_URL}/api/metrics...`);
  const res = http.get(`${BASE_URL}/api/metrics`);
  if (res.status === 200) {
    console.log(`[teardown] Final /api/metrics: ${res.body}`);
  }
}
