"use client";

import Link from "next/link";
import { signIn } from "next-auth/react";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";

type SignupResponse = {
  message?: string;
  user?: {
    id: string;
    email: string;
  };
  detail?: string;
};

interface SignupFormProps {
  googleEnabled: boolean;
}

function GoogleIcon({ className = "" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden className={className}>
      <path
        d="M21.35 11.1H12v2.95h5.37c-.24 1.5-1.8 4.4-5.37 4.4-3.23 0-5.87-2.68-5.87-5.98s2.64-5.98 5.87-5.98c1.84 0 3.07.78 3.78 1.45l2.58-2.5C16.72 3.92 14.57 3 12 3 7.03 3 3 7.03 3 12s4.03 9 9 9c5.2 0 8.64-3.65 8.64-8.79 0-.59-.06-1.03-.14-1.47Z"
        fill="#FFC107"
      />
      <path
        d="M4.04 7.82 6.47 9.6C7.12 8.06 8.43 6.95 12 6.95c1.84 0 3.07.78 3.78 1.45l2.58-2.5C16.72 3.92 14.57 3 12 3 8.42 3 5.29 5.04 4.04 7.82Z"
        fill="#FF3D00"
      />
      <path
        d="M12 21c2.5 0 4.6-.82 6.13-2.22l-2.83-2.32c-.76.54-1.78.92-3.3.92-3.49 0-5.11-2.36-5.5-3.55l-2.5 1.93C5.24 18.71 8.38 21 12 21Z"
        fill="#4CAF50"
      />
      <path
        d="M21.35 11.1H12v2.95h5.37c-.11.69-.49 1.71-1.42 2.39l.01-.01 2.83 2.32c-.2.18 1.85-1.35 1.85-5.07 0-.59-.06-1.03-.14-1.47Z"
        fill="#1976D2"
      />
    </svg>
  );
}

export function SignupForm({ googleEnabled }: SignupFormProps) {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [googleLoading, setGoogleLoading] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setLoading(true);

    try {
      const res = await fetch("/api/auth/signup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });

      const payload = (await res.json()) as SignupResponse;

      if (!res.ok) {
        const message = payload?.detail || "Unable to create account";
        setError(message);
        return;
      }

      router.push("/login?signup=success");
    } catch {
      setError("Network error. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  async function handleGoogle() {
    setError("");
    setGoogleLoading(true);
    await signIn("google", { callbackUrl: "/dashboard" });
    setGoogleLoading(false);
  }

  return (
    <div className="w-full max-w-md rounded-2xl border border-[#D6E2F5] bg-white p-7 text-[#091528] shadow-[0_10px_40px_rgba(9,21,40,0.12)]">
      <h1
        className="text-2xl font-extrabold tracking-tight"
        style={{ fontFamily: '"Bricolage Grotesque", Inter, sans-serif' }}
      >
        Create your account
      </h1>
      <p className="mt-2 text-sm text-[#4A6080]">Start posting from one dashboard in minutes.</p>

      {googleEnabled ? (
        <button
          type="button"
          onClick={handleGoogle}
          disabled={googleLoading}
          className="mt-5 flex w-full items-center justify-center gap-2 rounded-lg border border-[#D6E2F5] px-4 py-3 text-sm font-semibold text-[#091528] transition hover:bg-[#F4F8FF] disabled:cursor-not-allowed disabled:opacity-60"
        >
          <GoogleIcon className="h-4 w-4 shrink-0" />
          {googleLoading ? "Connecting..." : "Continue with Google"}
        </button>
      ) : null}

      <div className="my-5 flex items-center gap-3 text-xs uppercase tracking-[0.08em] text-[#7A94B0]">
        <div className="h-px flex-1 bg-[#D6E2F5]" />
        <span>Email signup</span>
        <div className="h-px flex-1 bg-[#D6E2F5]" />
      </div>

      <form onSubmit={handleSubmit} className="space-y-4">
        <label className="block">
          <span className="mb-1.5 block text-sm font-medium text-[#091528]">Email</span>
          <input
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            autoComplete="email"
            required
            className="w-full rounded-lg border border-[#D6E2F5] px-3 py-2.5 text-sm text-[#091528] outline-none transition focus:border-[#1D3FD0] focus:ring-2 focus:ring-[#1D3FD0]/20"
            placeholder="you@example.com"
          />
        </label>

        <label className="block">
          <span className="mb-1.5 block text-sm font-medium text-[#091528]">Password</span>
          <div className="relative">
            <input
              type={showPassword ? "text" : "password"}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="new-password"
              minLength={8}
              required
              className="w-full rounded-lg border border-[#D6E2F5] px-3 py-2.5 pr-20 text-sm text-[#091528] outline-none transition focus:border-[#1D3FD0] focus:ring-2 focus:ring-[#1D3FD0]/20"
              placeholder="At least 8 characters"
            />
            <button
              type="button"
              onClick={() => setShowPassword((current) => !current)}
              className="absolute right-2 top-1/2 -translate-y-1/2 rounded px-2 py-1 text-xs font-semibold text-[#1D3FD0] hover:bg-[#F4F8FF]"
            >
              {showPassword ? "Hide" : "Show"}
            </button>
          </div>
        </label>

        {error ? (
          <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>
        ) : null}

        <button
          type="submit"
          disabled={loading}
          className="w-full rounded-lg bg-[#1D3FD0] px-4 py-3 text-sm font-semibold text-white transition hover:bg-[#1633B8] disabled:cursor-not-allowed disabled:opacity-60"
        >
          {loading ? "Creating account..." : "Create account"}
        </button>
      </form>

      <p className="mt-5 text-sm text-[#4A6080]">
        Already have an account?{" "}
        <Link href="/login" className="font-semibold text-[#1D3FD0] hover:text-[#1633B8]">
          Sign in
        </Link>
      </p>

    </div>
  );
}
