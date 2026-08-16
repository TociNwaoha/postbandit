import type { MetadataRoute } from "next";
import { getAllPosts } from "@/lib/blog";
import { SITE_URL } from "@/lib/site";

const publicRoutes = ["/", "/developers", "/privacy", "/privacy-policy", "/terms", "/refunds", "/data-deletion", "/signup", "/blog"];

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const posts = await getAllPosts();

  return [
    ...publicRoutes.map((route) => ({ url: `${SITE_URL}${route}` })),
    ...posts.map((post) => ({ url: `${SITE_URL}/blog/${post.slug}`, lastModified: post.date })),
  ];
}
