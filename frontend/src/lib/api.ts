const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export type UserRole = "USER" | "ADMIN";

export interface CurrentUser {
  id: string;
  display_name: string;
  role: UserRole;
  onboarding_completed: boolean;
  created_at: string;
}

interface ApiFailure {
  detail?: string | { message?: string };
}

let accessToken = "";

export function apiUrl(path: string): string {
  return `${apiBaseUrl}/api/v1${path}`;
}

export function setAccessToken(token: string): void {
  accessToken = token;
}

export function clearAccessToken(): void {
  accessToken = "";
}

export async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
  if (options.body && !headers.has("Content-Type") && !(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(apiUrl(path), { ...options, headers, credentials: "include" });
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as ApiFailure;
    const detail = typeof body.detail === "string" ? body.detail : body.detail?.message;
    throw new Error(detail || "요청을 처리하지 못했습니다.");
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export async function restoreSession(): Promise<CurrentUser> {
  const response = await apiFetch<{ access_token: string; user: CurrentUser }>("/auth/access-token", {
    method: "POST",
  });
  setAccessToken(response.access_token);
  // 앱 진입 시 JWT 발급 결과만 신뢰하지 않고, 현재 사용자 정보를 다시 조회한다.
  // 역할이 바뀌었거나 온보딩이 완료된 뒤에도 헤더와 진입 화면을 최신 상태로 맞춘다.
  return apiFetch<CurrentUser>("/auth/me");
}
