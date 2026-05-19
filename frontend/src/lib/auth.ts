import type { NextAuthOptions } from "next-auth";
import CredentialsProvider from "next-auth/providers/credentials";
import GoogleProvider from "next-auth/providers/google";

import { SERVER_API_URL } from "@/lib/serverApi";

const SESSION_MAX_AGE_SECONDS = 5 * 24 * 60 * 60;

type BackendAuthResponse = {
  access_token: string;
  user: {
    id: string;
    email: string;
    tier: string;
  };
};

async function exchangeGoogleIdToken(idToken: string): Promise<BackendAuthResponse | null> {
  try {
    const res = await fetch(`${SERVER_API_URL}/api/auth/google/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id_token: idToken }),
      cache: "no-store",
    });

    if (!res.ok) return null;
    return (await res.json()) as BackendAuthResponse;
  } catch {
    return null;
  }
}

const providers: NextAuthOptions["providers"] = [
  CredentialsProvider({
    name: "credentials",
    credentials: {
      email: { label: "Email", type: "email" },
      password: { label: "Password", type: "password" },
    },
    async authorize(credentials) {
      if (!credentials?.email || !credentials?.password) return null;

      try {
        const res = await fetch(`${SERVER_API_URL}/api/auth/login`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            email: credentials.email,
            password: credentials.password,
          }),
          cache: "no-store",
        });

        if (!res.ok) return null;

        const data = await res.json();
        return {
          id: data.user.id,
          email: data.user.email,
          accessToken: data.access_token,
          tier: data.user.tier,
        };
      } catch {
        return null;
      }
    },
  }),
];

if (process.env.GOOGLE_CLIENT_ID && process.env.GOOGLE_CLIENT_SECRET) {
  providers.push(
    GoogleProvider({
      clientId: process.env.GOOGLE_CLIENT_ID,
      clientSecret: process.env.GOOGLE_CLIENT_SECRET,
    })
  );
}

export const authOptions: NextAuthOptions = {
  providers,
  callbacks: {
    async signIn({ user, account }) {
      if (account?.provider !== "google") return true;

      const idToken = typeof account.id_token === "string" ? account.id_token : "";
      if (!idToken) return false;

      const exchange = await exchangeGoogleIdToken(idToken);
      if (!exchange) return false;

      (user as any).id = exchange.user.id;
      (user as any).email = exchange.user.email;
      (user as any).accessToken = exchange.access_token;
      (user as any).tier = exchange.user.tier;
      return true;
    },
    async jwt({ token, user, account }) {
      if (user) {
        token.sub = (user as any).id ?? token.sub;
        token.email = user.email ?? token.email;
        token.accessToken = (user as any).accessToken ?? token.accessToken;
        token.tier = (user as any).tier ?? token.tier;
      }

      if (account?.provider === "google" && !token.accessToken) {
        const idToken = typeof account.id_token === "string" ? account.id_token : "";
        if (idToken) {
          const exchange = await exchangeGoogleIdToken(idToken);
          if (exchange) {
            token.sub = exchange.user.id;
            token.email = exchange.user.email;
            token.accessToken = exchange.access_token;
            token.tier = exchange.user.tier;
          }
        }
      }

      return token;
    },
    async session({ session, token }) {
      (session as any).accessToken = token.accessToken;
      if (session.user) {
        (session.user as any).tier = token.tier;
        (session.user as any).id = token.sub;
      }
      return session;
    },
  },
  pages: {
    signIn: "/login",
  },
  session: {
    strategy: "jwt",
    maxAge: SESSION_MAX_AGE_SECONDS,
  },
  secret: process.env.NEXTAUTH_SECRET,
};
