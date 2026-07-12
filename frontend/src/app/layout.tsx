import type { Metadata } from "next";
import "./globals.css";
import { Providers } from "./providers";

const APP_TITLE = "PostBandit";
const APP_DESCRIPTION = "AI-powered video clipping and social publishing for creators";
const APP_ICON = "/icon.png";

export const metadata: Metadata = {
  metadataBase: new URL("https://postbandit.com"),
  title: APP_TITLE,
  description: APP_DESCRIPTION,
  icons: {
    icon: "/favicon.ico",
    apple: APP_ICON,
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
    <html lang="en" className="dark">
      <body className="bg-[#0F172A] text-white antialiased">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
