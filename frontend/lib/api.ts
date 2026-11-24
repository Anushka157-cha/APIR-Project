const API =
  process.env.NEXT_PUBLIC_API_URL ||
  (typeof window !== "undefined" && window.location.hostname.includes("railway.app")
    ? "https://soothing-perception-production-f9d1989d.up.railway.app"
    : typeof window !== "undefined" && window.location.hostname !== "localhost" && window.location.hostname !== "127.0.0.1"
    ? `http://${window.location.hostname}:8000`
    : "http://localhost:8000");

export function token(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("apir_token");
}

export async function api(path: string, init: RequestInit = {}) {
  const t = token();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init.headers as Record<string, string>),
  };
  if (t) headers.Authorization = `Bearer ${t}`;
  const res = await fetch(`${API}${path}`, { ...init, headers });
  if (res.status === 401 && typeof window !== "undefined") {
    localStorage.removeItem("apir_token");
    if (!path.includes("/auth/login")) window.location.href = "/login";
  }
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || res.statusText);
  }
  return res.json();
}
