"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";

export default function LoginPage() {
  const [username, setUsername] = useState("sre");
  const [password, setPassword] = useState("sre123");
  const [error, setError] = useState("");
  const router = useRouter();

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    try {
      const data = await api("/auth/login", {
        method: "POST",
        body: JSON.stringify({ username, password }),
      });
      localStorage.setItem("apir_token", data.access_token);
      localStorage.setItem("apir_role", data.role);
      router.push("/dashboard");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "login failed");
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center">
      <form onSubmit={onSubmit} className="w-full max-w-sm rounded-xl border border-line bg-card p-8">
        <h1 className="text-xl font-semibold">APIR console</h1>
        <p className="mt-1 text-sm text-neutral-400">SRE login — demo users in README</p>
        <label className="mt-6 block text-xs uppercase text-neutral-500">Username</label>
        <input
          className="mt-1 w-full rounded border border-line bg-panel px-3 py-2"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
        />
        <label className="mt-4 block text-xs uppercase text-neutral-500">Password</label>
        <input
          type="password"
          className="mt-1 w-full rounded border border-line bg-panel px-3 py-2"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        {error && <p className="mt-3 text-sm text-bad">{error}</p>}
        <button className="mt-6 w-full rounded bg-accent py-2 font-medium text-black">Sign in</button>
      </form>
    </div>
  );
}
