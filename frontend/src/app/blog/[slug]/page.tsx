import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { compileMDX } from "next-mdx-remote/rsc";
import remarkGfm from "remark-gfm";
import { BlogFooter } from "@/components/marketing/BlogFooter";
import { BlogHeader } from "@/components/marketing/BlogHeader";
import { getAllSlugs, getPostBySlug } from "@/lib/blog";
import { SITE_URL } from "@/lib/site";

type BlogPostPageProps = {
  params: { slug: string };
};

export const dynamic = "force-static";

export async function generateStaticParams() {
  const slugs = await getAllSlugs();
  return slugs.map((slug) => ({ slug }));
}

export async function generateMetadata({ params }: BlogPostPageProps): Promise<Metadata> {
  const post = await getPostBySlug(params.slug);
  if (!post) return {};

  const url = `${SITE_URL}/blog/${post.slug}`;
  const image = `${url}/opengraph-image`;

  return {
    title: `${post.title} | PostBandit`,
    description: post.description,
    alternates: { canonical: url },
    openGraph: {
      title: post.title,
      description: post.description,
      type: "article",
      publishedTime: post.date,
      url,
      images: [{ url: image, width: 1200, height: 630, alt: post.title }],
    },
    twitter: {
      card: "summary_large_image",
      title: post.title,
      description: post.description,
      images: [image],
    },
  };
}

export default async function BlogPostPage({ params }: BlogPostPageProps) {
  const post = await getPostBySlug(params.slug);
  if (!post) notFound();

  const { content } = await compileMDX({
    source: post.content,
    options: { mdxOptions: { remarkPlugins: [remarkGfm] } },
  });
  const url = `${SITE_URL}/blog/${post.slug}`;
  const image = `${url}/opengraph-image`;
  const structuredData = {
    "@context": "https://schema.org",
    "@type": "Article",
    headline: post.title,
    description: post.description,
    datePublished: post.date,
    dateModified: post.date,
    author: { "@type": "Person", name: post.author },
    publisher: { "@type": "Organization", name: "PostBandit", url: SITE_URL },
    mainEntityOfPage: { "@type": "WebPage", "@id": url },
    image,
  };

  return (
    <div className="min-h-screen bg-[#F6FAFF] text-[#091528]">
      <BlogHeader />
      <main className="mx-auto w-full max-w-3xl px-7 py-14 sm:py-20">
        <article>
          <p className="text-sm font-semibold text-[#1D3FD0]">{post.category}</p>
          <h1 className="mt-3 text-4xl font-extrabold leading-tight tracking-tight sm:text-5xl">{post.title}</h1>
          <p className="mt-5 text-lg leading-8 text-[#4A6080]">{post.description}</p>
          <div className="mt-6 flex flex-wrap gap-x-3 gap-y-1 text-sm text-[#7A94B0]">
            <span>{post.author}</span><span aria-hidden>•</span><span>{post.date}</span><span aria-hidden>•</span><span>{post.readTime}</span>
          </div>
          <div className="prose prose-slate mt-12 max-w-none prose-headings:text-[#091528] prose-p:text-[#334C6C] prose-a:text-[#1D3FD0] prose-a:font-semibold prose-strong:text-[#091528] prose-th:bg-[#EDF4FF] prose-th:text-[#16356B] prose-td:border-[#D6E2F5] prose-th:border-[#D6E2F5]">
            {content}
          </div>
        </article>
      </main>
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(structuredData) }} />
      <BlogFooter />
    </div>
  );
}
