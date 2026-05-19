import type { Metadata } from "next";
import { Bricolage_Grotesque, Plus_Jakarta_Sans } from "next/font/google";

const bricolage = Bricolage_Grotesque({ subsets: ["latin"], weight: ["700", "800"] });
const jakarta = Plus_Jakarta_Sans({ subsets: ["latin"], weight: ["400", "500", "600", "700"] });

const EFFECTIVE_DATE = "May 16, 2026";

export const metadata: Metadata = {
  title: "Privacy Policy | PostBandit",
  description: "PostBandit Privacy Policy",
  alternates: {
    canonical: "https://postbandit.com/privacy",
  },
};

export default function PrivacyPage() {
  return (
    <main className={`${jakarta.className} min-h-screen bg-[#F6FAFF] px-4 py-10 text-[#091528] sm:px-6`}>
      <div className="mx-auto w-full max-w-4xl rounded-3xl border border-[#D6E2F5] bg-white p-6 shadow-[0_12px_28px_rgba(9,21,40,0.08)] sm:p-8">
        <header className="mb-8 border-b border-[#E2ECFA] pb-6">
          <div className="flex items-center gap-3">
            <img src="/icon.png" alt="PostBandit logo" width={40} height={40} className="h-10 w-10 rounded-lg" />
            <p className={`${bricolage.className} text-2xl font-extrabold tracking-tight text-[#1D3FD0]`}>PostBandit</p>
          </div>
          <h1 className={`${bricolage.className} mt-5 text-3xl font-extrabold tracking-tight text-[#091528] sm:text-4xl`}>
            Privacy Policy
          </h1>
          <p className="mt-2 text-sm text-[#4A6080]">Effective date: {EFFECTIVE_DATE}</p>
        </header>

        <div className="space-y-7 text-sm leading-7 text-[#334C6C] sm:text-base">
          <section>
            <h2 className="text-xl font-semibold text-[#091528]">1. Information We Collect</h2>
            <p className="mt-2">
              We collect account details (email and authentication data), uploaded video content, generated clips and
              captions, and operational metadata required to run your workflow.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-[#091528]">2. How We Use Data</h2>
            <p className="mt-2">
              We use data to provide the PostBandit service: ingesting media, generating transcripts and clips,
              creating exports, and publishing content to platforms you explicitly connect and select.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-[#091528]">3. Cookies and Session Data</h2>
            <p className="mt-2">
              PostBandit uses essential cookies and session tokens to keep you authenticated and secure your account.
              We do not use these mechanisms to sell personal information.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-[#091528]">4. Third-Party Services</h2>
            <p className="mt-2">
              We integrate with third-party providers for storage, authentication, and social publishing. When you
              publish content, required data is shared with the selected provider to complete that action.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-[#091528]">5. Data Retention and Security</h2>
            <p className="mt-2">
              We retain data for service operations, reliability, and account history. Tokens are encrypted at rest,
              and access is restricted to authorized systems and operators.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-[#091528]">6. Your Rights</h2>
            <p className="mt-2">
              You can request access, correction, or deletion of your account-related data by contacting support. You
              can also disconnect linked social accounts in the app at any time.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-[#091528]">7. Contact</h2>
            <p className="mt-2">
              For privacy requests or questions, contact <span className="font-semibold text-[#091528]">support@postbandit.com</span>.
            </p>
          </section>
        </div>
      </div>
    </main>
  );
}
