import Link from "next/link";
import { BlogFooter } from "@/components/marketing/BlogFooter";
import { BlogHeader } from "@/components/marketing/BlogHeader";
import { getAllPosts } from "@/lib/blog";

function formatDate(date: string): string {
  return new Intl.DateTimeFormat("en-US", { dateStyle: "long", timeZone: "UTC" }).format(new Date(`${date}T00:00:00Z`));
}

export default async function BlogIndexPage() {
  const posts = await getAllPosts();

  return (
    <div className="min-h-screen bg-[#F6FAFF] text-[#091528]">
      <BlogHeader />
      <main className="mx-auto w-full max-w-[1160px] px-7 py-16 sm:py-20">
        <h1 className="text-4xl font-extrabold tracking-tight sm:text-5xl">Blog</h1>
        {posts.length === 0 ? (
          <p className="mt-10 text-base text-[#4A6080]">No posts published yet.</p>
        ) : (
          <div className="mt-10 grid gap-5 md:grid-cols-2">
            {posts.map((post) => (
              <article key={post.slug} className="rounded-2xl border border-[#D6E2F5] bg-white p-6 transition hover:border-[#9DBBEC] hover:shadow-[0_10px_30px_rgba(9,21,40,0.08)]">
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs font-semibold text-[#1D3FD0]">
                  <span>{post.category}</span>
                  <span className="text-[#7A94B0]">{formatDate(post.date)}</span>
                  <span className="text-[#7A94B0]">{post.readTime}</span>
                </div>
                <h2 className="mt-4 text-2xl font-bold leading-tight tracking-tight text-[#091528]">
                  <Link href={`/blog/${post.slug}`} className="transition hover:text-[#1D3FD0]">{post.title}</Link>
                </h2>
                <p className="mt-3 leading-7 text-[#4A6080]">{post.description}</p>
              </article>
            ))}
          </div>
        )}
      </main>
      <BlogFooter />
    </div>
  );
}
