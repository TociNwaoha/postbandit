import { LoginForm } from "@/components/auth/LoginForm";
import Link from "next/link";

interface LoginPageProps {
  searchParams?: {
    signup?: string;
    settings?: string;
  };
}

export default function LoginPage({ searchParams }: LoginPageProps) {
  const googleEnabled = Boolean(process.env.GOOGLE_CLIENT_ID && process.env.GOOGLE_CLIENT_SECRET);
  const signupSuccess = searchParams?.signup === "success";
  const settingsMessage =
    searchParams?.settings === "email-updated"
      ? "Email updated. Sign in with your new email."
      : searchParams?.settings === "password-updated"
        ? "Password updated. Sign in again."
        : null;

  return (
    <main
      className="relative min-h-[100dvh] overflow-hidden bg-[linear-gradient(180deg,#1D3FD0_0%,#1734AE_100%)] text-white"
      style={{ fontFamily: '"Plus Jakarta Sans", Inter, sans-serif' }}
    >
      <div className="pointer-events-none absolute inset-0">
        <div
          className="absolute inset-0 opacity-[0.16]"
          style={{
            backgroundImage:
              "linear-gradient(rgba(255,255,255,0.2) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.2) 1px, transparent 1px)",
            backgroundSize: "34px 34px",
          }}
        />
        <div
          className="absolute -left-20 top-16 h-72 w-72 rounded-full bg-[#7AA8FF]/35 blur-3xl motion-safe:animate-pulse"
          style={{ animationDuration: "7s" }}
        />
        <div
          className="absolute right-[-5rem] top-[-2rem] h-80 w-80 rounded-full bg-[#5A7CFF]/30 blur-3xl motion-safe:animate-pulse"
          style={{ animationDelay: "1.5s", animationDuration: "9s" }}
        />
        <div
          className="absolute bottom-[-6rem] left-[38%] h-72 w-72 rounded-full bg-[#0F206B]/40 blur-3xl motion-safe:animate-pulse"
          style={{ animationDelay: "0.7s", animationDuration: "11s" }}
        />
      </div>

      <div className="mx-auto grid min-h-[100dvh] w-full max-w-[1160px] gap-12 px-7 py-24 md:grid-cols-[1.1fr_0.9fr] md:items-center">
        <section className="relative z-10">
          <p className="inline-flex items-center rounded-full border border-white/20 bg-white/12 px-4 py-1.5 text-xs font-semibold uppercase tracking-[0.08em] text-white/90 backdrop-blur">
            Welcome back
          </p>
          <div className="mt-5 inline-flex items-center gap-3">
            <div className="h-10 w-10 rounded-xl bg-[#1D3FD0] ring-1 ring-white/35 flex items-center justify-center">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M5 3L19 12L5 21V3Z" fill="white" />
              </svg>
            </div>
            <span
              className="text-3xl font-extrabold tracking-tight text-white"
              style={{ fontFamily: '"Bricolage Grotesque", Inter, sans-serif' }}
            >
              PostBandit
            </span>
          </div>
          <h1
            className="mt-6 text-4xl font-extrabold leading-tight tracking-[-0.03em] md:text-5xl"
            style={{ fontFamily: '"Bricolage Grotesque", Inter, sans-serif' }}
          >
            Sign in and keep your publishing workflow moving.
          </h1>
          <p className="mt-5 max-w-xl text-base leading-7 text-white/80">
            Continue clipping, exporting, and publishing from your unified PostBandit dashboard.
          </p>
          <div className="mt-7 flex flex-wrap gap-2.5 text-xs font-semibold uppercase tracking-[0.06em] text-white/80">
            <span className="rounded-full border border-white/20 bg-white/10 px-3 py-1">Fast clip editing</span>
            <span className="rounded-full border border-white/20 bg-white/10 px-3 py-1">Multi-platform publishing</span>
            <span className="rounded-full border border-white/20 bg-white/10 px-3 py-1">Live queue visibility</span>
          </div>
          <div className="mt-8 flex flex-wrap items-center gap-4 text-sm text-white/80">
            <Link href="/" className="rounded-lg border border-white/25 px-4 py-2 font-semibold hover:bg-white/10">
              Back to landing
            </Link>
            <Link href="/privacy" className="underline underline-offset-4 hover:text-white">
              Privacy Policy
            </Link>
            <Link href="/terms" className="underline underline-offset-4 hover:text-white">
              Terms of Service
            </Link>
          </div>
        </section>

        <section className="relative z-10 flex justify-center md:justify-end">
          <div className="w-full max-w-md">
            <LoginForm googleEnabled={googleEnabled} />

            {signupSuccess ? (
              <div className="mt-4 rounded-lg border border-emerald-300/35 bg-emerald-400/15 px-3 py-2 text-sm text-emerald-100">
                Account created. Sign in to continue.
              </div>
            ) : null}
            {settingsMessage ? (
              <div className="mt-4 rounded-lg border border-emerald-300/35 bg-emerald-400/15 px-3 py-2 text-sm text-emerald-100">
                {settingsMessage}
              </div>
            ) : null}

            <div className="mt-4 text-center text-sm text-white/80">
              New here?{" "}
              <Link href="/signup" className="font-medium text-white underline underline-offset-4 hover:text-white/90">
                Create an account
              </Link>
            </div>
            <p className="mt-4 text-center text-xs leading-5 text-white/75">
              By signing in you agree to our{" "}
              <Link href="/terms" className="underline underline-offset-4 hover:text-white">
                Terms of Service
              </Link>{" "}
              and{" "}
              <Link href="/privacy" className="underline underline-offset-4 hover:text-white">
                Privacy Policy
              </Link>
              .
            </p>
          </div>
        </section>
      </div>
    </main>
  );
}
