import type { Metadata } from "next";
import { Bricolage_Grotesque, Plus_Jakarta_Sans } from "next/font/google";

const bricolage = Bricolage_Grotesque({ subsets: ["latin"], weight: ["700", "800"] });
const jakarta = Plus_Jakarta_Sans({ subsets: ["latin"], weight: ["400", "500", "600", "700"] });

const EFFECTIVE_DATE = "May 16, 2026";

export const metadata: Metadata = {
  title: "Terms of Service | PostBandit",
  description: "PostBandit Terms of Service",
  alternates: {
    canonical: "https://postbandit.com/terms",
  },
};

export default function TermsPage() {
  return (
    <main className={`${jakarta.className} min-h-screen bg-[#F6FAFF] px-4 py-10 text-[#091528] sm:px-6`}>
      <div className="mx-auto w-full max-w-4xl rounded-3xl border border-[#D6E2F5] bg-white p-6 shadow-[0_12px_28px_rgba(9,21,40,0.08)] sm:p-8">
        <header className="mb-8 border-b border-[#E2ECFA] pb-6">
          <div className="flex items-center gap-3">
            <img src="/icon.png" alt="PostBandit logo" width={40} height={40} className="h-10 w-10 rounded-lg" />
            <p className={`${bricolage.className} text-2xl font-extrabold tracking-tight text-[#1D3FD0]`}>PostBandit</p>
          </div>
          <h1 className={`${bricolage.className} mt-5 text-3xl font-extrabold tracking-tight text-[#091528] sm:text-4xl`}>
            Terms of Service
          </h1>
          <p className="mt-2 text-sm text-[#4A6080]">Effective date: {EFFECTIVE_DATE}</p>
        </header>

        <div className="space-y-7 text-sm leading-7 text-[#334C6C] sm:text-base">
          <section>
            <h2 className="text-xl font-semibold text-[#091528]">1. Acceptance of Terms</h2>
            <p className="mt-2">
              By using PostBandit, you agree to these Terms and our Privacy Policy. If you do not agree, do not use
              the service.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-[#091528]">2. Account Responsibilities</h2>
            <p className="mt-2">
              You are responsible for safeguarding your account credentials and for actions taken through your account,
              including social publishing actions initiated from PostBandit.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-[#091528]">3. Content and Usage Rights</h2>
            <p className="mt-2">
              You must have rights to upload, process, and publish content through PostBandit. You retain ownership of
              your content, and you grant PostBandit the limited rights necessary to process it for requested features.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-[#091528]">4. Acceptable Use</h2>
            <p className="mt-2">
              You may not use PostBandit for unlawful activity, abuse of third-party platform policies, attempts to
              compromise service security, or infringement of intellectual property rights.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-[#091528]">5. Third-Party Platforms</h2>
            <p className="mt-2">
              Publishing integrations depend on third-party APIs and platform rules. PostBandit does not guarantee
              acceptance, reach, or availability of external platform features.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-[#091528]">6. Service Availability and Changes</h2>
            <p className="mt-2">
              We may update, suspend, or discontinue features as needed for reliability, compliance, or product
              evolution. We may also update these Terms and will revise the effective date when changes are posted.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-[#091528]">7. Contact</h2>
            <p className="mt-2">
              For terms questions, contact <span className="font-semibold text-[#091528]">support@postbandit.com</span>.
            </p>
          </section>
        </div>
      </div>
    </main>
  );
}
