"use client";

import { useState } from "react";
import { signIn } from "next-auth/react";
import { useRouter } from "next/navigation";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";

interface LoginFormProps {
  googleEnabled?: boolean;
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

export function LoginForm({ googleEnabled = false }: LoginFormProps) {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [googleLoading, setGoogleLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      const result = await signIn("credentials", {
        email,
        password,
        redirect: false,
      });

      if (result?.error) {
        setError("Invalid email or password");
      } else {
        router.push("/dashboard");
        router.refresh();
      }
    } catch {
      setError("Something went wrong. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  async function handleGoogleSignIn() {
    setError("");
    setGoogleLoading(true);
    await signIn("google", { callbackUrl: "/dashboard" });
    setGoogleLoading(false);
  }

  return (
    <Card className="rounded-2xl border-[#D6E2F5] p-7 shadow-[0_10px_40px_rgba(9,21,40,0.12)]">
      <h2
        className="mb-1 text-2xl font-extrabold tracking-tight text-[#091528]"
        style={{ fontFamily: '"Bricolage Grotesque", Inter, sans-serif' }}
      >
        Sign in
      </h2>
      <p className="mb-6 text-sm text-[#4A6080]">Welcome back to PostBandit.</p>

      <form onSubmit={handleSubmit} className="space-y-4">
        <Input
          label="Email"
          type="email"
          placeholder="you@example.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
          autoComplete="email"
        />
        <Input
          label="Password"
          type="password"
          placeholder="••••••••"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
          autoComplete="current-password"
        />

        {error && (
          <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2.5 text-sm text-red-700">
            {error}
          </div>
        )}

        <Button type="submit" loading={loading} className="w-full mt-2" size="lg">
          Sign in
        </Button>
      </form>

      {googleEnabled && (
        <>
          <div className="my-5 flex items-center gap-3">
            <div className="h-px flex-1 bg-[#D6E2F5]" />
            <span className="text-xs uppercase tracking-[0.08em] text-[#7A94B0]">or</span>
            <div className="h-px flex-1 bg-[#D6E2F5]" />
          </div>

          <Button
            type="button"
            variant="secondary"
            size="lg"
            className="w-full gap-2.5"
            loading={googleLoading}
            onClick={handleGoogleSignIn}
          >
            <GoogleIcon className="h-4 w-4 shrink-0" />
            Continue with Google
          </Button>
        </>
      )}
    </Card>
  );
}
