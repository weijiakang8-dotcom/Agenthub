import http from "k6/http";
import { check, sleep } from "k6";

export const options = {
  scenarios: {
    load: {
      executor: "constant-vus",
      vus: Number(__ENV.VUS || 10),
      duration: "30s",
    },
  },
  thresholds: {
    http_req_failed: ["rate<0.05"],
    http_req_duration: ["p(95)<2000", "p(99)<5000"],
  },
};

const BASE_URL = __ENV.BASE_URL || "http://127.0.0.1:8000";
const WORKFLOW_ID = __ENV.WORKFLOW_ID || "";

export default function () {
  const payload = JSON.stringify({
    workflow_id: WORKFLOW_ID,
    user_input: "压测：请简单介绍一下 LangGraph",
  });

  const res = http.post(`${BASE_URL}/api/executions`, payload, {
    headers: { "Content-Type": "application/json" },
  });

  check(res, {
    "execution accepted (202)": (r) => r.status === 202,
  });

  sleep(1);
}
