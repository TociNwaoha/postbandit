import type { Metadata } from "next";
import { Bricolage_Grotesque, Plus_Jakarta_Sans } from "next/font/google";
import "./globals.css";
import { Providers } from "./providers";

const display = Bricolage_Grotesque({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-display",
});

const body = Plus_Jakarta_Sans({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-body",
});

const APP_TITLE = "PostBandit";
const APP_DESCRIPTION = "AI-powered video clipping and social publishing for creators";
const APP_ICON = "/icon-512.png";

export const metadata: Metadata = {
  metadataBase: new URL("https://postbandit.com"),
  title: APP_TITLE,
  description: APP_DESCRIPTION,
  icons: {
    icon: [
      { url: "/icon-32.png", sizes: "32x32", type: "image/png" },
      { url: "/icon-16.png", sizes: "16x16", type: "image/png" },
      { url: "/icon-192.png", sizes: "192x192", type: "image/png" },
    ],
    apple: [
      { url: "/icon-180.png", sizes: "180x180", type: "image/png" },
    ],
    shortcut: "/favicon.ico",
    other: [
      { rel: "icon", url: "/icon-512.png", sizes: "512x512" },
    ],
  },
  openGraph: {
    title: APP_TITLE,
    description: APP_DESCRIPTION,
    url: "https://postbandit.com",
    siteName: APP_TITLE,
    images: [
      {
        url: APP_ICON,
        width: 512,
        height: 512,
        alt: "PostBandit",
      },
    ],
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: APP_TITLE,
    description: APP_DESCRIPTION,
    images: [APP_ICON],
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`dark ${display.variable} ${body.variable}`}>
      <body className="bg-[#0F172A] text-white antialiased">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
