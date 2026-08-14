import type { Metadata } from "next";

const EFFECTIVE_DATE = "August 14, 2026";
const LAST_UPDATED = "August 14, 2026";

export const metadata: Metadata = {
  title: "User Data Deletion | PostBandit",
  description: "How to request deletion of your PostBandit account and connected platform data.",
  alternates: {
    canonical: "https://postbandit.com/data-deletion",
  },
};

export default function DataDeletionPage() {
  return (
    <main className="app-body min-h-screen bg-[#F6FAFF] px-4 py-10 text-[#091528] sm:px-6">
      <div className="mx-auto w-full max-w-4xl rounded-3xl border border-[#D6E2F5] bg-white p-6 shadow-[0_12px_28px_rgba(9,21,40,0.08)] sm:p-8">
        <header className="mb-8 border-b border-[#E2ECFA] pb-6">
          <div className="flex items-center gap-3">
            <img src="/icon-512.png" alt="PostBandit logo" width={40} height={40} className="h-10 w-10 rounded-lg" />
            <p className="app-display text-2xl font-extrabold tracking-tight text-[#1D3FD0]">PostBandit</p>
          </div>
          <h1 className="app-display mt-5 text-3xl font-extrabold tracking-tight text-[#091528] sm:text-4xl">
            User Data Deletion Instructions
          </h1>
          <p className="mt-2 text-sm text-[#4A6080]">
            Effective Date: {EFFECTIVE_DATE} | Last Updated: {LAST_UPDATED}
          </p>
        </header>

        <div className="space-y-7 text-sm leading-7 text-[#334C6C] sm:text-base">
          <p>
            This page explains how to request deletion of your PostBandit account data and connected social platform data.
          </p>

          <section>
            <h2 className="text-xl font-semibold text-[#091528]">1. Delete Your Account</h2>
            <p className="mt-2">
              Email <span className="font-semibold text-[#091528]">postbanditsupport@gmail.com</span> from the email address associated with your PostBandit account and use the subject line <span className="font-semibold text-[#091528]">&quot;Delete My Account&quot;</span>.
            </p>
            <p className="mt-2">
              In your message, include your account email address and a clear request to delete your PostBandit account and associated data.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-[#091528]">2. What We Delete</h2>
            <ul className="mt-3 list-disc space-y-2 pl-6">
              <li>Your PostBandit account profile information</li>
              <li>Connected social platform OAuth tokens</li>
              <li>Saved platform connections and publish settings</li>
              <li>Uploaded source media that has not already been removed by our processing workflow</li>
              <li>Associated transcripts, clips, captions, and generated social copy tied to your account</li>
            </ul>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-[#091528]">3. What May Be Retained</h2>
            <p className="mt-2">
              We may retain limited records where required for legal, tax, fraud prevention, billing dispute, security, or compliance purposes. Payment card details are not stored by PostBandit and are handled by Stripe.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-[#091528]">4. Timing</h2>
            <p className="mt-2">
              We aim to respond to deletion requests within 30 days. Connected social platform tokens are removed when the platform is disconnected or when your account deletion request is completed.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-[#091528]">5. Alternative Option</h2>
            <p className="mt-2">
              If you only want to remove a connected social account without deleting your full PostBandit account, disconnect that platform from your account settings or contact support for help.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-[#091528]">6. Contact</h2>
            <p className="mt-2">Deletion requests and privacy questions: postbanditsupport@gmail.com</p>
            <p className="mt-2 font-semibold text-[#091528]">BANDAMONT LLC | postbandit.com</p>
          </section>
        </div>
      </div>
    </main>
  );
}
