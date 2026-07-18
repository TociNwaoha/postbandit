import type { Metadata } from "next";

const EFFECTIVE_DATE = "July 10, 2026";
const LAST_UPDATED = "July 10, 2026";

export const metadata: Metadata = {
  title: "Terms of Service | PostBandit",
  description: "PostBandit Terms of Service",
  alternates: {
    canonical: "https://postbandit.com/terms",
  },
};

export default function TermsPage() {
  return (
    <main className="app-body min-h-screen bg-[#F6FAFF] px-4 py-10 text-[#091528] sm:px-6">
      <div className="mx-auto w-full max-w-4xl rounded-3xl border border-[#D6E2F5] bg-white p-6 shadow-[0_12px_28px_rgba(9,21,40,0.08)] sm:p-8">
        <header className="mb-8 border-b border-[#E2ECFA] pb-6">
          <div className="flex items-center gap-3">
            <img src="/icon.png" alt="PostBandit logo" width={40} height={40} className="h-10 w-10 rounded-lg" />
            <p className="app-display text-2xl font-extrabold tracking-tight text-[#1D3FD0]">PostBandit</p>
          </div>
          <h1 className="app-display mt-5 text-3xl font-extrabold tracking-tight text-[#091528] sm:text-4xl">
            PostBandit Terms of Service
          </h1>
          <p className="mt-2 text-sm text-[#4A6080]">
            Effective Date: {EFFECTIVE_DATE} | Last Updated: {LAST_UPDATED}
          </p>
        </header>

        <div className="space-y-7 text-sm leading-7 text-[#334C6C] sm:text-base">
          <p>
            These Terms of Service (&quot;Terms&quot;) govern your access to and use of PostBandit (&quot;Service&quot;), operated by BANDAMONT LLC (&quot;PostBandit,&quot; &quot;we,&quot; &quot;us,&quot; or &quot;our&quot;). By creating an account or using the Service, you agree to these Terms. If you do not agree, do not use the Service.
          </p>

          <section>
            <h2 className="text-xl font-semibold text-[#091528]">1. The Service</h2>
            <p className="mt-2">
              PostBandit is a content automation platform that allows you to import video content, generate short-form clips using artificial intelligence, add caption overlays, write platform-specific copy, and publish or schedule posts to connected social media platforms including YouTube, TikTok, Instagram, X (formerly Twitter), Facebook, and Threads. The specific features available to you depend on your subscription plan.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-[#091528]">2. Eligibility and Accounts</h2>
            <p className="mt-2">
              You must be at least 18 years old to use PostBandit. By creating an account, you represent that you meet this requirement and that all information you provide is accurate and current.
            </p>
            <p className="mt-2">
              You are responsible for maintaining the confidentiality of your account credentials and for all activity that occurs under your account. Notify us immediately at postbanditsupport@gmail.com if you suspect unauthorized access.
            </p>
            <p className="mt-2">
              You may not create multiple accounts to circumvent plan limits, trial restrictions, or any suspension or termination of your account.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-[#091528]">3. Subscriptions and Billing</h2>
            <p className="mt-2">
              PostBandit offers paid subscription plans (Creator, Pro, and Elite) with different feature sets and usage limits. Current pricing is displayed at postbandit.com/pricing.
            </p>
            <p className="mt-2">
              New subscribers receive a 7-day free trial. A valid payment method is required to start your trial. You will not be charged until the trial period ends. If you cancel before the trial ends, you will not be charged.
            </p>
            <p className="mt-2">
              Subscriptions are billed monthly on the same date as your trial end date. We use Stripe to process payments. By subscribing, you authorize us to charge your payment method on a recurring basis until you cancel.
            </p>
            <p className="mt-2">Plan changes take effect immediately. Upgrades are prorated. Downgrades take effect at the start of the next billing period.</p>
            <p className="mt-2">
              If a payment fails, we will retry automatically. We will notify you by email. Your account will remain accessible during the retry period. If payment is not resolved within 7 days of the failed charge, your account may be restricted to read-only access until payment is updated.
            </p>
            <p className="mt-2">Prices do not include applicable taxes. You are responsible for any taxes applicable to your subscription.</p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-[#091528]">4. Cancellation</h2>
            <p className="mt-2">
              You may cancel your subscription at any time from your account&apos;s billing page or by contacting postbanditsupport@gmail.com. Cancellation takes effect at the end of your current billing period. You will retain access to the Service until that date.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-[#091528]">5. Acceptable Use</h2>
            <p className="mt-2">You agree not to use PostBandit to:</p>
            <ul className="mt-3 list-disc space-y-2 pl-6">
              <li>Upload, process, or publish content that infringes any third party&apos;s intellectual property rights, including copyrighted music, video, or images you do not have rights to use</li>
              <li>Publish spam, misleading content, or content that violates the terms of service of any social platform you connect</li>
              <li>Harass, threaten, or harm any individual or group</li>
              <li>Upload malware, viruses, or any code designed to interfere with the Service</li>
              <li>Attempt to reverse engineer, scrape, or circumvent any security measures of the Service</li>
              <li>Use the API to build a competing product</li>
              <li>Share your API keys with third parties or allow others to use your account to circumvent usage limits</li>
            </ul>
            <p className="mt-3">We reserve the right to suspend or terminate accounts that violate these terms without notice and without refund.</p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-[#091528]">6. Your Content</h2>
            <p className="mt-2">
              You retain all ownership rights to the content you upload, generate, or publish through PostBandit. We do not claim ownership of your videos, clips, captions, or posts.
            </p>
            <p className="mt-2">
              By uploading content to PostBandit, you grant us a limited, non-exclusive, royalty-free license to store, process, transcribe, clip, render, and transmit your content solely for the purpose of providing the Service to you. This license ends when your content is deleted.
            </p>
            <p className="mt-2">
              You are solely responsible for the content you upload and publish. You represent that you have all necessary rights, licenses, and permissions to use that content and to publish it to connected social platforms.
            </p>
            <p className="mt-2">
              PostBandit uses artificial intelligence to generate clip suggestions, caption text, and social media copy. AI outputs are provided as suggestions. You are responsible for reviewing and approving all content before it is published.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-[#091528]">7. Social Platform Integrations</h2>
            <p className="mt-2">
              PostBandit connects to third-party social platforms via OAuth. By connecting a platform account, you authorize PostBandit to publish content to that account on your behalf, agree to comply with the terms of service of each connected platform, and acknowledge that PostBandit is not responsible for actions taken by social platforms, including content removal, account suspension, or changes to their APIs that may affect the Service. Social platforms may reject, delay, or remove content at their discretion. PostBandit does not guarantee successful publication to any platform.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-[#091528]">8. API Access</h2>
            <p className="mt-2">
              API access is available on Pro and Elite plans. By using the PostBandit API, you agree to keep your API keys confidential, stay within the rate limits of your plan, use the API only to automate your own PostBandit workflows, and accept that exceeding rate limits will result in temporary blocking until your limit window resets. We reserve the right to revoke API access for abuse or violation of these terms.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-[#091528]">9. Data and Content Deletion</h2>
            <p className="mt-2">
              PostBandit uses a process-then-delete workflow for video files. Uploaded or imported video files are processed and then deleted from our servers after export and publication. If you cancel your subscription, your account data is retained for 90 days before permanent deletion. You may request immediate deletion by emailing postbanditsupport@gmail.com. OAuth tokens for connected social platforms are encrypted at rest and deleted immediately when you disconnect a platform or delete your account.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-[#091528]">10. Copyright and DMCA</h2>
            <p className="mt-2">
              We respect intellectual property rights. If you believe content published through PostBandit infringes your copyright, please send a DMCA takedown notice to postbanditsupport@gmail.com with your contact information, identification of the copyrighted work, identification of the infringing content, a statement of good faith belief, a statement under penalty of perjury that the information is accurate, and your physical or electronic signature. We will respond to valid notices promptly. Repeat infringers will have their accounts terminated.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-[#091528]">11. Intellectual Property</h2>
            <p className="mt-2">
              PostBandit, its logo, design, software, and all associated technology are owned by BANDAMONT LLC and protected by intellectual property laws. These Terms do not grant you any rights to our trademarks, patents, or proprietary technology beyond the limited right to use the Service as described.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-[#091528]">12. Limitation of Liability</h2>
            <p className="mt-2 uppercase">
              To the maximum extent permitted by law, PostBandit and its officers, employees, and affiliates shall not be liable for any indirect, incidental, special, consequential, or punitive damages, including but not limited to loss of profits, lost data, failed publications, or social platform suspensions, arising from your use of the Service. Our total liability to you for any claim arising from these Terms or your use of the Service shall not exceed the amount you paid us in the 3 months preceding the claim.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-[#091528]">13. Disclaimer of Warranties</h2>
            <p className="mt-2 uppercase">
              The Service is provided &quot;as is&quot; and &quot;as available&quot; without warranties of any kind. We do not warrant that the Service will be uninterrupted, error-free, or that AI output will be accurate or suitable for your purposes.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-[#091528]">14. Termination</h2>
            <p className="mt-2">
              We may suspend or terminate your access to the Service at any time for violation of these Terms, non-payment, or any conduct we determine to be harmful to the Service or other users. You may terminate your account at any time by cancelling your subscription and emailing postbanditsupport@gmail.com to request deletion.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-[#091528]">15. Changes to These Terms</h2>
            <p className="mt-2">
              We may update these Terms from time to time. We will notify you of material changes by email or by posting a notice in your dashboard. Continued use of the Service after changes take effect constitutes acceptance of the updated Terms.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-[#091528]">16. Governing Law</h2>
            <p className="mt-2">These Terms are governed by the laws of Massachusetts, without regard to conflict of law principles. Any disputes will be resolved in the courts of Massachusetts.</p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-[#091528]">17. Contact</h2>
            <p className="mt-2">For questions about these Terms: postbanditsupport@gmail.com</p>
            <p className="mt-2 font-semibold text-[#091528]">BANDAMONT LLC | postbandit.com</p>
          </section>
        </div>
      </div>
    </main>
  );
}
