import type { AccessTokenResponse, InterviewResultResponse, StartInterviewResponse, WebSocketTokenResponse } from "./types";

const PERSONAL_EMAIL_DOMAINS = new Set([
  "gmail.com",
  "googlemail.com",
  "yahoo.com",
  "outlook.com",
  "hotmail.com",
  "live.com",
  "icloud.com",
  "aol.com",
  "protonmail.com",
  "pm.me",
  "mail.com",
  "gmx.com",
  "zoho.com",
  "yandex.com"
]);

function normalizeBaseUrl(url: string) {
  return String(url || "").trim().replace(/\/+$/, "");
}

function isLocalHostname(hostname: string) {
  const normalized = String(hostname || "").trim().toLowerCase();
  return normalized === "localhost" || normalized === "127.0.0.1" || normalized === "::1";
}

function getDefaultApiBaseUrl() {
  if (typeof window !== "undefined" && isLocalHostname(window.location.hostname)) {
    return "http://localhost:8000";
  }
  return "";
}

const API_BASE_URL = normalizeBaseUrl(process.env.NEXT_PUBLIC_API_BASE_URL ?? getDefaultApiBaseUrl());
const WS_BASE_URL = normalizeBaseUrl(
  process.env.NEXT_PUBLIC_WS_BASE_URL ??
    API_BASE_URL.replace("https://", "wss://").replace("http://", "ws://")
);

type RecruiterAccessState = {
  allowed: boolean;
  message: string;
};

type StartInterviewPayload = {
  candidate_name: string;
  role: string;
  interview_type: "mixed" | "technical" | "behavioral";
};

function decodeJwtPayload(token: string): Record<string, unknown> {
  const parts = String(token || "").split(".");
  if (parts.length < 2) {
    return {};
  }
  const encodedPayload = parts[1].replace(/-/g, "+").replace(/_/g, "/");
  const padded = encodedPayload.padEnd(Math.ceil(encodedPayload.length / 4) * 4, "=");
  try {
    if (typeof window === "undefined") {
      return JSON.parse(Buffer.from(padded, "base64").toString("utf-8")) as Record<string, unknown>;
    }
    return JSON.parse(window.atob(padded)) as Record<string, unknown>;
  } catch {
    return {};
  }
}

function getStringClaim(payload: Record<string, unknown>, keys: string[]) {
  for (const key of keys) {
    const value = String(payload[key] ?? "").trim();
    if (value) {
      return value;
    }
  }
  return "";
}

function extractEmailDomain(email: string) {
  const cleaned = String(email || "").trim().toLowerCase();
  if (!cleaned.includes("@")) {
    return "";
  }
  return cleaned.split("@")[1] || "";
}

function isUniversityEmailDomain(domain: string) {
  const cleaned = String(domain || "").trim().toLowerCase();
  if (!cleaned) {
    return false;
  }
  return cleaned.endsWith(".edu") || cleaned.includes(".edu.") || cleaned.includes(".ac.");
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  if (!API_BASE_URL) {
    throw new Error("Missing NEXT_PUBLIC_API_BASE_URL. Configure it in your deployment environment.");
  }
  const response = await fetch(`${API_BASE_URL}${path}`, init);
  if (!response.ok) {
    const errorPayload = await response.json().catch(() => ({}));
    throw new Error(errorPayload.error ?? errorPayload.detail ?? response.statusText ?? "Request failed");
  }
  return (await response.json()) as T;
}

export function getClientAccessToken() {
  if (typeof window === "undefined") {
    return "";
  }
  const tokenFromStorage = String(window.localStorage.getItem("zoswi_access_token") || "").trim();
  return tokenFromStorage;
}

export function getRecruiterAccessState(accessToken?: string): RecruiterAccessState {
  const token = String(accessToken || getClientAccessToken()).trim();
  if (!token) {
    return {
      allowed: false,
      message: "Sign in with a recruiter account to access recruiter board."
    };
  }

  const payload = decodeJwtPayload(token);
  const role = getStringClaim(payload, ["role"]).toLowerCase();
  if (role !== "recruiter" && role !== "admin") {
    return {
      allowed: false,
      message: "Recruiter board is available only for recruiter or admin accounts."
    };
  }

  const email = getStringClaim(payload, ["email", "user_email", "preferred_username", "upn"]).toLowerCase();
  const domain = extractEmailDomain(email);
  if (domain && (PERSONAL_EMAIL_DOMAINS.has(domain) || isUniversityEmailDomain(domain))) {
    return {
      allowed: false,
      message: "Recruiter board is restricted to organization email domains."
    };
  }

  return { allowed: true, message: "" };
}

function buildAuthHeaders(accessToken?: string): Record<string, string> {
  const token = String(accessToken || getClientAccessToken()).trim();
  if (!token) {
    return {};
  }
  return { Authorization: `Bearer ${token}` };
}

export function startInterview(payload: StartInterviewPayload, accessToken?: string) {
  return request<StartInterviewResponse>("/start-interview", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...buildAuthHeaders(accessToken) },
    body: JSON.stringify(payload)
  });
}

export function getInterviewResult(sessionId: string, accessToken?: string) {
  const params = new URLSearchParams({ session_id: sessionId });
  return request<InterviewResultResponse>(`/interview-result?${params.toString()}`, {
    method: "GET",
    headers: { ...buildAuthHeaders(accessToken) },
    cache: "no-store"
  });
}

export function createWebSocketToken(sessionId: string, accessToken?: string) {
  return request<WebSocketTokenResponse>("/auth/ws-token", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...buildAuthHeaders(accessToken) },
    body: JSON.stringify({ session_id: sessionId })
  });
}

export function exchangeStreamlitLaunchToken(launchToken: string) {
  return request<AccessTokenResponse>("/auth/streamlit-launch", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ launch_token: launchToken })
  });
}

export function getRecruiterCandidates(params?: { role?: string; min_score?: number }, accessToken?: string) {
  const query = new URLSearchParams();
  if (params?.role) {
    query.set("role", params.role);
  }
  if (typeof params?.min_score === "number") {
    query.set("min_score", String(params.min_score));
  }
  return request(`/recruiter/candidates${query.size > 0 ? `?${query.toString()}` : ""}`, {
    method: "GET",
    headers: { ...buildAuthHeaders(accessToken) },
    cache: "no-store"
  });
}

export function getRecruiterInterviews(params?: { role?: string; min_score?: number }, accessToken?: string) {
  const query = new URLSearchParams();
  if (params?.role) {
    query.set("role", params.role);
  }
  if (typeof params?.min_score === "number") {
    query.set("min_score", String(params.min_score));
  }
  return request(`/recruiter/interviews${query.size > 0 ? `?${query.toString()}` : ""}`, {
    method: "GET",
    headers: { ...buildAuthHeaders(accessToken) },
    cache: "no-store"
  });
}

export function getRecruiterInterview(sessionId: string, accessToken?: string) {
  return request(`/recruiter/interviews/${sessionId}`, {
    method: "GET",
    headers: { ...buildAuthHeaders(accessToken) },
    cache: "no-store"
  });
}

export function getRecruiterReplay(sessionId: string, accessToken?: string) {
  return request(`/recruiter/interviews/${sessionId}/replay`, {
    method: "GET",
    headers: { ...buildAuthHeaders(accessToken) },
    cache: "no-store"
  });
}

export function getRecruiterScorecard(sessionId: string, accessToken?: string) {
  return request(`/recruiter/interviews/${sessionId}/scorecard`, {
    method: "GET",
    headers: { ...buildAuthHeaders(accessToken) },
    cache: "no-store"
  });
}

export function postRecruiterReview(
  sessionId: string,
  payload: { decision: string; notes?: string; override_recommendation?: boolean },
  accessToken?: string
) {
  return request(`/recruiter/interviews/${sessionId}/review`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...buildAuthHeaders(accessToken) },
    body: JSON.stringify(payload)
  });
}

export function getInterviewWebSocketUrl(path = "/ws/interview", params?: Record<string, string>) {
  if (!WS_BASE_URL) {
    throw new Error("Missing NEXT_PUBLIC_WS_BASE_URL. Configure it in your deployment environment.");
  }
  const query = new URLSearchParams(params || {}).toString();
  if (!query) {
    return `${WS_BASE_URL}${path}`;
  }
  return `${WS_BASE_URL}${path}?${query}`;
}
