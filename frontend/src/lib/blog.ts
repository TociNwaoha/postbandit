import { readdir, readFile } from "fs/promises";
import path from "path";
import matter from "gray-matter";

const BLOG_DIRECTORY = path.join(process.cwd(), "content", "blog");

export type BlogPost = {
  title: string;
  slug: string;
  description: string;
  date: string;
  category: string;
  author: string;
  readTime: string;
  keywords: string[];
  pillar?: boolean;
  content: string;
};

function getString(data: Record<string, unknown>, key: string): string | null {
  const value = data[key];
  return typeof value === "string" ? value : null;
}

function parsePost(source: string, filename: string): BlogPost | null {
  const { data, content } = matter(source);
  const fields = ["title", "slug", "description", "date", "category", "author", "readTime"] as const;
  const values = fields.map((field) => getString(data, field));

  if (values.some((value) => value === null)) return null;

  const [title, slug, description, date, category, author, readTime] = values as string[];
  if (slug !== path.basename(filename, ".mdx")) return null;

  const keywords = Array.isArray(data.keywords)
    ? data.keywords.filter((keyword): keyword is string => typeof keyword === "string")
    : [];

  return {
    title,
    slug,
    description,
    date,
    category,
    author,
    readTime,
    keywords,
    ...(typeof data.pillar === "boolean" ? { pillar: data.pillar } : {}),
    content,
  };
}

function isPublished(post: BlogPost): boolean {
  return post.date <= new Date().toISOString().slice(0, 10);
}

async function readPosts(): Promise<BlogPost[]> {
  let filenames: string[];

  try {
    filenames = await readdir(BLOG_DIRECTORY);
  } catch {
    return [];
  }

  const posts = await Promise.all(
    filenames
      .filter((filename) => filename.endsWith(".mdx"))
      .map(async (filename) => {
        const source = await readFile(path.join(BLOG_DIRECTORY, filename), "utf8");
        return parsePost(source, filename);
      }),
  );

  return posts.filter((post): post is BlogPost => post !== null);
}

export async function getAllPosts(): Promise<BlogPost[]> {
  const posts = await readPosts();
  return posts.filter(isPublished).sort((first, second) => second.date.localeCompare(first.date));
}

export async function getPostBySlug(slug: string): Promise<BlogPost | null> {
  const posts = await getAllPosts();
  return posts.find((post) => post.slug === slug) ?? null;
}

export async function getAllSlugs(): Promise<string[]> {
  const posts = await getAllPosts();
  return posts.map((post) => post.slug);
}
