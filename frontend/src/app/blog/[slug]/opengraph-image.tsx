import { ImageResponse } from "next/og";
import { getPostBySlug } from "@/lib/blog";

export const runtime = "nodejs";
export const dynamic = "force-static";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default async function OpenGraphImage({ params }: { params: { slug: string } }) {
  const post = await getPostBySlug(params.slug);
  const title = post?.title ?? "PostBandit";

  return new ImageResponse(
    (
      <div style={{ alignItems: "stretch", background: "#0F172A", color: "white", display: "flex", flexDirection: "column", height: "100%", justifyContent: "space-between", padding: "72px", width: "100%", fontFamily: "Inter, system-ui, sans-serif" }}>
        <div style={{ color: "#8BB3FF", display: "flex", fontSize: 34, fontWeight: 700 }}>PostBandit</div>
        <div style={{ display: "flex", fontSize: 64, fontWeight: 800, letterSpacing: "-2px", lineHeight: 1.08, maxWidth: "980px", overflow: "hidden" }}>{title}</div>
        <div style={{ color: "#B8CAE9", display: "flex", fontSize: 26 }}>postbandit.com/blog</div>
      </div>
    ),
    size,
  );
}
