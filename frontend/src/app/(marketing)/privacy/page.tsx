import type { Metadata } from "next";

const EFFECTIVE_DATE = "July 10, 2026";
const LAST_UPDATED = "July 10, 2026";

export const metadata: Metadata = {
  title: "Privacy Policy | PostBandit",
  description: "PostBandit Privacy Policy",
  alternates: {
    canonical: "https://postbandit.com/privacy",
  },
};

export default function PrivacyPage() {
  return (
    <main className="app-body min-h-screen bg-[#F6FAFF] px-4 py-10 text-[#091528] sm:px-6">
      <div className="mx-auto w-full max-w-4xl rounded-3xl border border-[#D6E2F5] bg-white p-6 shadow-[0_12px_28px_rgba(9,21,40,0.08)] sm:p-8">
        <header className="mb-8 border-b border-[#E2ECFA] pb-6">
          <div className="flex items-center gap-3">
            <img src="/icon.png" alt="PostBandit logo" width={40} height={40} className="h-10 w-10 rounded-lg" />
            <p className="app-display text-2xl font-extrabold tracking-tight text-[#1D3FD0]">PostBandit</p>
          </div>
          <h1 className="app-display mt-5 text-3xl font-extrabold tracking-tight text-[#091528] sm:text-4xl">
            PostBandit Privacy Policy
          </h1>
          <p className="mt-2 text-sm text-[#4A6080]">
            Effective Date: {EFFECTIVE_DATE} | Last Updated: {LAST_UPDATED}
          </p>
        </header>

        <div className="space-y-7 text-sm leading-7 text-[#334C6C] sm:text-base">
          <p>
            This Privacy Policy explains how BANDAMONT LLC (&quot;PostBandit,&quot; &quot;we,&quot; &quot;us,&quot; or &quot;our&quot;) collects, uses, and protects your information when you use PostBandit (postbandit.com).
          </p>

          <section>
            <h2 className="text-xl font-semibold text-[#091528]">1. Information We Collect</h2>
            <p className="mt-2"><span className="font-semibold text-[#091528]">Account Information:</span> When you create an account: name, email address, and password (hashed — we never store plaintext passwords).</p>
            <p className="mt-2"><span className="font-semibold text-[#091528]">Payment Information:</span> We use Stripe to process payments. We do not store your card number, CVC, or full payment details. Stripe stores this information under their own privacy policy (stripe.com/privacy). We store your Stripe customer ID and subscription status to manage your account.</p>
            <p className="mt-2"><span className="font-semibold text-[#091528]">Connected Social Accounts:</span> When you connect a social media account, we receive and store OAuth access tokens that allow us to publish content on your behalf. These tokens are encrypted at rest. We access only the permissions required to publish content — we do not read your followers, messages, or private data.</p>
            <p className="mt-2"><span className="font-semibold text-[#091528]">Content You Upload:</span> Videos you upload or import, transcripts generated from those videos, clips you create, captions, and social media copy. Source video files are deleted after processing. Transcripts and clip data are retained while your account is active.</p>
            <p className="mt-2"><span className="font-semibold text-[#091528]">Usage Data:</span> Log data including pages visited, features used, API calls made, error events, and timestamps.</p>
            <p className="mt-2"><span className="font-semibold text-[#091528]">Device and Browser Information:</span> IP address, browser type, operating system, and referral URL.</p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-[#091528]">2. How We Use Your Information</h2>
            <p className="mt-2">
              We use your information to provide, operate, and maintain the Service; process your subscription and manage billing; publish content to your connected social accounts; generate AI-powered clip suggestions, captions, and social copy; send transactional emails; monitor and improve Service performance; detect and prevent fraud and security incidents; respond to support requests; and comply with legal obligations.
            </p>
            <p className="mt-2">We do not sell your personal information. We do not use your content to train AI models.</p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-[#091528]">3. Third-Party Services</h2>
            <p className="mt-2">We share data with the following third parties only as necessary to operate the Service:</p>
            <ul className="mt-3 list-disc space-y-2 pl-6">
              <li>Stripe — Payment processing (stripe.com/privacy)</li>
              <li>YouTube / Google — Publishing to YouTube (policies.google.com/privacy)</li>
              <li>TikTok — Publishing to TikTok (tiktok.com/legal/privacy-policy)</li>
              <li>Meta (Instagram, Facebook, Threads) — Publishing to Meta platforms (facebook.com/privacy/policy)</li>
              <li>X Corp — Publishing to X (twitter.com/privacy)</li>
              <li>DeepSeek — AI copy generation (deepseek.com)</li>
              <li>Sentry — Error monitoring (sentry.io/privacy)</li>
              <li>Backblaze / Cloudflare — Cloud storage (backblaze.com/company/privacy)</li>
            </ul>
            <p className="mt-3">We do not share your data with advertising networks or data brokers.</p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-[#091528]">4. Data Retention</h2>
            <p className="mt-2">
              Source video files are deleted after processing and export. Transcripts and clip data are retained while your account is active. Publish history is retained while your account is active. OAuth tokens are deleted when you disconnect the platform or delete your account. Account data after cancellation is retained for 90 days, then permanently deleted. Payment records are retained for 7 years (legal/tax requirement). Usage logs are retained for 12 months.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-[#091528]">5. Security</h2>
            <p className="mt-2">
              OAuth tokens are encrypted at rest. All data is transmitted over HTTPS. Payment processing is handled by Stripe (PCI-DSS compliant). API keys are stored as SHA-256 hashes — plaintext keys are shown only once and never stored. Access to production systems is restricted and monitored.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-[#091528]">6. Your Rights</h2>
            <p className="mt-2">You may request to access, correct, delete, or export your personal data by emailing postbanditsupport@gmail.com. We will respond within 30 days.</p>
            <p className="mt-2"><span className="font-semibold text-[#091528]">California Residents (CCPA):</span> You have the right to know what personal information we collect, to delete it, and to opt out of its sale (we do not sell personal information).</p>
            <p className="mt-2"><span className="font-semibold text-[#091528]">EU/UK Residents (GDPR):</span> Our legal basis for processing your data is performance of a contract, legitimate interest, and your consent where applicable. You have the right to lodge a complaint with your local data protection authority.</p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-[#091528]">7. Cookies</h2>
            <p className="mt-2">We use essential cookies required for authentication and session management. We do not use advertising cookies or third-party tracking cookies.</p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-[#091528]">8. Children&apos;s Privacy</h2>
            <p className="mt-2">PostBandit is not directed to children under 18. We do not knowingly collect personal information from anyone under 18.</p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-[#091528]">9. Changes to This Policy</h2>
            <p className="mt-2">We will notify you of material changes by email or dashboard notice at least 14 days before they take effect.</p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-[#091528]">10. Contact</h2>
            <p className="mt-2">Privacy questions or requests: postbanditsupport@gmail.com</p>
            <p className="mt-2 font-semibold text-[#091528]">BANDAMONT LLC | postbandit.com</p>
          </section>
        </div>
      </div>
    </main>
  );
}
