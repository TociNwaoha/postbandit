import { NextRequest, NextResponse } from "next/server";
import { SERVER_API_URL } from "@/lib/serverApi";

export async function POST(request: NextRequest) {
  let payload: unknown;

  try {
    payload = await request.json();
  } catch {
    return NextResponse.json({ detail: "Invalid JSON payload" }, { status: 400 });
  }

  try {
    const response = await fetch(`${SERVER_API_URL}/api/auth/signup`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      cache: "no-store",
    });

    const text = await response.text();
    const isJson = response.headers.get("content-type")?.includes("application/json");
    const body = isJson && text ? JSON.parse(text) : { detail: text || "Request failed" };

    return NextResponse.json(body, { status: response.status });
  } catch {
    return NextResponse.json({ detail: "Unable to reach signup service" }, { status: 502 });
  }
}
