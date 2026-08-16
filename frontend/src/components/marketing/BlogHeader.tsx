import Link from "next/link";

export function BlogHeader() {
  return (
    <header className="border-b border-[#D6E2F5] bg-[rgba(246,250,255,0.92)]">
      <div className="mx-auto flex h-16 w-full max-w-[1160px] items-center justify-between px-7">
        <Link href="/" className="text-2xl font-extrabold tracking-tight" aria-label="PostBandit home">
          <span className="text-[#1D3FD0]">Post</span>
          <span className="text-[#091528]">Bandit</span>
        </Link>
        <div className="flex items-center gap-4">
          <Link href="/blog" className="text-sm font-semibold text-[#4A6080] transition hover:text-[#1D3FD0]">
            Blog
          </Link>
          <Link href="/login" className="hidden text-sm font-semibold text-[#4A6080] transition hover:text-[#091528] sm:inline-flex">
            Log in
          </Link>
          <Link href="/signup" className="rounded-lg bg-[#1D3FD0] px-4 py-2 text-sm font-semibold text-white transition hover:bg-[#1633B8]">
            Start free
          </Link>
        </div>
      </div>
    </header>
  );
}
