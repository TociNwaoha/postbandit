import Link from "next/link";

export function BlogFooter() {
  return (
    <footer className="bg-[#0D1A33] py-10 text-white">
      <div className="mx-auto flex w-full max-w-[1160px] flex-col items-center justify-between gap-5 px-7 text-center md:flex-row md:text-left">
        <Link href="/" className="text-lg font-extrabold">
          <span className="text-[#7EA7FF]">Post</span>
          <span>Bandit</span>
        </Link>
        <div className="flex items-center gap-5 text-sm text-white/50">
          <Link href="/privacy" className="transition hover:text-white">Privacy</Link>
          <Link href="/terms" className="transition hover:text-white">Terms</Link>
          <Link href="/data-deletion" className="transition hover:text-white">Data deletion</Link>
          <Link href="/refunds" className="transition hover:text-white">Refunds</Link>
        </div>
        <p className="text-[13px] text-white/30">© 2026 PostBandit. All rights reserved.</p>
      </div>
    </footer>
  );
}
