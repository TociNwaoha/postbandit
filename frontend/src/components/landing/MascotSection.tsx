"use client";

import Link from "next/link";
import { MouseEvent, useEffect, useRef, useState } from "react";

export function MascotSection() {
  const [isLightboxMounted, setIsLightboxMounted] = useState(false);
  const [isLightboxVisible, setIsLightboxVisible] = useState(false);
  const closeTimerRef = useRef<number | null>(null);

  const openLightbox = () => {
    if (closeTimerRef.current) {
      window.clearTimeout(closeTimerRef.current);
      closeTimerRef.current = null;
    }
    setIsLightboxMounted(true);
    window.requestAnimationFrame(() => setIsLightboxVisible(true));
  };

  const closeLightbox = () => {
    setIsLightboxVisible(false);
    closeTimerRef.current = window.setTimeout(() => {
      setIsLightboxMounted(false);
      closeTimerRef.current = null;
    }, 300);
  };

  useEffect(() => {
    if (!isLightboxMounted) return;

    const originalOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") closeLightbox();
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = originalOverflow;
      if (closeTimerRef.current) {
        window.clearTimeout(closeTimerRef.current);
        closeTimerRef.current = null;
      }
    };
  }, [isLightboxMounted]);

  const handleOverlayClick = (event: MouseEvent<HTMLDivElement>) => {
    if (event.target === event.currentTarget) closeLightbox();
  };

  return (
    <section className="relative overflow-hidden bg-[#1D3FD0] py-[108px] text-white">
      <div
        aria-hidden="true"
        className="absolute inset-0"
        style={{
          backgroundImage:
            "radial-gradient(rgba(255,255,255,0.07) 1px, transparent 1px), radial-gradient(ellipse at 30% 50%, rgba(255,255,255,0.08), transparent 58%)",
          backgroundSize: "30px 30px, 100% 100%",
        }}
      />

      <div className="relative mx-auto grid w-full max-w-[1160px] items-center gap-20 px-7 md:grid-cols-2 max-[860px]:grid-cols-1">
        <div className="relative mx-auto w-full max-w-[400px] max-[860px]:max-w-full max-[860px]:px-4">
          <button
            type="button"
            onClick={openLightbox}
            className="mascot-video-trigger group relative block w-full cursor-pointer rounded-[28px] focus:outline-none focus:ring-4 focus:ring-white/35"
            aria-label="Watch the full PostBandit mascot video"
          >
            <video
              src="/bandit.mp4"
              autoPlay
              loop
              muted
              playsInline
              className="mascot-video h-auto w-full rounded-[28px] object-cover shadow-[0_24px_72px_rgba(0,0,0,0.35)] transition duration-300 ease-out group-hover:scale-[1.04] group-hover:translate-y-[-4px] group-hover:shadow-[0_34px_96px_rgba(0,0,0,0.48)]"
            />
            <span className="absolute bottom-[-18px] left-1/2 -translate-x-1/2 whitespace-nowrap rounded-full bg-white px-4 py-2 text-sm font-bold text-[#1D3FD0] shadow-[0_10px_28px_rgba(0,0,0,0.22)]">
              Click to watch full video
            </span>
          </button>
        </div>

        <div className="max-[860px]:text-center">
          <div className="mb-5 inline-flex rounded-full border border-white/25 bg-white/[0.14] px-4 py-2 text-sm font-bold text-white">
            🦝 Meet Bandit
          </div>
          <h2 className="font-[family-name:var(--font-bricolage)] text-[clamp(26px,3.5vw,46px)] font-extrabold leading-[1.04] tracking-[-1.5px] text-white">
            Your content deserves a crew that never sleeps.
          </h2>
          <p className="mt-4 max-w-xl text-[17px] font-normal leading-[1.76] text-white/70 max-[860px]:mx-auto">
            Bandit is the PostBandit mascot — and just like him, the platform is quick, sharp, and always working behind the scenes so you don&apos;t have to.
          </p>
          <Link
            href="/signup"
            className="mt-8 inline-flex rounded-[10px] bg-white px-7 py-3.5 text-base font-bold text-[#1D3FD0] shadow-[0_4px_20px_rgba(0,0,0,0.18)] transition duration-200 hover:-translate-y-0.5 hover:shadow-[0_10px_28px_rgba(0,0,0,0.22)]"
          >
            Start posting free →
          </Link>
        </div>
      </div>

      {isLightboxMounted ? (
        <div
          className={`fixed inset-0 z-[1000] flex items-center justify-center bg-black/[0.92] p-6 transition-opacity duration-300 ${
            isLightboxVisible ? "opacity-100" : "opacity-0"
          }`}
          onMouseDown={handleOverlayClick}
          role="dialog"
          aria-modal="true"
          aria-label="PostBandit mascot video"
        >
          <button
            type="button"
            onClick={closeLightbox}
            className="absolute right-6 top-6 flex h-11 w-11 items-center justify-center rounded-full bg-white/[0.12] text-2xl leading-none text-white transition hover:bg-white/20 focus:outline-none focus:ring-4 focus:ring-white/25"
            aria-label="Close mascot video"
          >
            ×
          </button>
          <video src="/bandit.mp4" controls autoPlay playsInline className="max-h-[86vh] max-w-[92vw] rounded-[28px] shadow-[0_32px_110px_rgba(0,0,0,0.65)]" />
        </div>
      ) : null}

      <style jsx>{`
        @keyframes bandit-float {
          0%,
          100% {
            transform: translateY(0px);
          }
          50% {
            transform: translateY(-16px);
          }
        }

        .mascot-video-trigger {
          animation: bandit-float 5s ease-in-out infinite;
        }
      `}</style>
    </section>
  );
}
