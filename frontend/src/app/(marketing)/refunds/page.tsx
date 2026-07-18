import type { Metadata } from "next";

const EFFECTIVE_DATE = "July 10, 2026";

export const metadata: Metadata = {
  title: "Refund Policy | PostBandit",
  description: "PostBandit Refund Policy",
  alternates: {
    canonical: "https://postbandit.com/refunds",
  },
};

export default function RefundPolicyPage() {
  return (
    <main className="app-body min-h-screen bg-[#F6FAFF] px-4 py-10 text-[#091528] sm:px-6">
      <div className="mx-auto w-full max-w-4xl rounded-3xl border border-[#D6E2F5] bg-white p-6 shadow-[0_12px_28px_rgba(9,21,40,0.08)] sm:p-8">
        <header className="mb-8 border-b border-[#E2ECFA] pb-6">
          <div className="flex items-center gap-3">
            <img src="/icon.png" alt="PostBandit logo" width={40} height={40} className="h-10 w-10 rounded-lg" />
            <p className="app-display text-2xl font-extrabold tracking-tight text-[#1D3FD0]">PostBandit</p>
          </div>
          <h1 className="app-display mt-5 text-3xl font-extrabold tracking-tight text-[#091528] sm:text-4xl">
            PostBandit Refund Policy
          </h1>
          <p className="mt-2 text-sm text-[#4A6080]">Effective Date: {EFFECTIVE_DATE}</p>
        </header>

        <div className="space-y-7 text-sm leading-7 text-[#334C6C] sm:text-base">
          <section>
            <h2 className="text-xl font-semibold text-[#091528]">Free Trial</h2>
            <p className="mt-2">
              All PostBandit plans include a 7-day free trial. A valid payment method is required to start your trial. You will not be charged during the trial period. If you cancel before your trial ends, you will not be charged anything.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-[#091528]">Cancellations</h2>
            <p className="mt-2">
              You may cancel your subscription at any time from your billing page or by emailing postbanditsupport@gmail.com. Cancellations take effect at the end of your current billing period. You will retain full access to the Service until that date. We do not offer partial refunds for unused time in a billing period.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-[#091528]">Refund Eligibility</h2>
            <p className="mt-2">
              We will issue a full refund if you were charged after cancelling before your trial ended due to a billing error; you were charged twice for the same billing period due to a technical error; or you contact us within 48 hours of your first charge (after trial) and have not used the Service to publish any content.
            </p>
            <p className="mt-2">
              We do not issue refunds for change of mind after the trial period; unused time remaining in a billing period after cancellation; failure to cancel before the trial ends; social platform rejections or API changes outside our control; or dissatisfaction with AI output quality.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-[#091528]">How to Request a Refund</h2>
            <p className="mt-2">
              Email postbanditsupport@gmail.com with subject line &quot;Refund Request&quot; and include your account email, the charge date and amount, and the reason for your request. We respond within 2 business days. Approved refunds are processed within 5–10 business days.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-[#091528]">Disputes and Chargebacks</h2>
            <p className="mt-2">
              If you believe a charge was made in error, please contact us at postbanditsupport@gmail.com before initiating a chargeback. Chargebacks filed without contacting us first may result in account suspension while the dispute is investigated.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-[#091528]">Contact</h2>
            <p className="mt-2">Billing questions: postbanditsupport@gmail.com</p>
            <p className="mt-2 font-semibold text-[#091528]">BANDAMONT LLC | postbandit.com</p>
          </section>
        </div>
      </div>
    </main>
  );
}
