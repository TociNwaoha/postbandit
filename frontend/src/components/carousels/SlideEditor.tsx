"use client";

import { useEffect, useMemo, useState } from "react";

import { SlidePreview } from "@/components/carousels/SlidePreview";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { api, ApiError } from "@/lib/api";
import {
  CarouselConfig,
  CarouselExport,
  CarouselGenerateResponse,
  CarouselRenderResponse,
  CarouselSlide,
  CarouselTemplate,
  ContentQueueItem,
} from "@/types";

const GLOW_OPTIONS = ["corners", "left", "right", "spread", "top-right"];

function defaultSlides(): CarouselSlide[] {
  return [
    { type: "hook", text: "Hook headline with *accent*", subtitle: "Supporting subtitle", glow: "corners" },
    { type: "body", title: "Core point", bullets: ["Bullet one", "Bullet two", "Bullet three"], glow: "left" },
    { type: "body", title: "Another point", text: "Short body text", glow: "right" },
    { type: "body", title: "Proof", bullets: ["Stat one", "Stat two"], glow: "spread" },
    { type: "body", title: "Actionable step", text: "What to do next", glow: "corners" },
    {
      type: "cta",
      text: "Ready for the full system?",
      cta_action: 'Comment *"GUIDE"* and I\'ll DM you the link',
      glow: "top-right",
    },
  ];
}

function defaultConfig(templateRenderer?: string): CarouselConfig {
  return {
    title: "New Carousel",
    profile: { display_name: "PostBandit Creator", handle: "@postbandit" },
    renderer: templateRenderer || null,
    slides: defaultSlides(),
  };
}

function readFileAsBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const value = reader.result;
      if (typeof value !== "string") {
        reject(new Error("Failed to encode file"));
        return;
      }
      resolve(value);
    };
    reader.onerror = () => reject(new Error("Failed to read file"));
    reader.readAsDataURL(file);
  });
}

interface SlideEditorProps {
  initialTemplateId?: string;
  initialQueueItemId?: string;
}

export function SlideEditor({ initialTemplateId, initialQueueItemId }: SlideEditorProps) {
  const [templates, setTemplates] = useState<CarouselTemplate[]>([]);
  const [selectedTemplateId, setSelectedTemplateId] = useState(initialTemplateId || "");
  const [topic, setTopic] = useState("");
  const [config, setConfig] = useState<CarouselConfig>(defaultConfig());
  const [referenceImages, setReferenceImages] = useState<Record<string, string>>({});
  const [renderResult, setRenderResult] = useState<CarouselRenderResponse | null>(null);
  const [savedExport, setSavedExport] = useState<CarouselExport | null>(null);

  const [loadingTemplates, setLoadingTemplates] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [rendering, setRendering] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [loadingQueueItem, setLoadingQueueItem] = useState(false);
  const [isPreloadedPreview, setIsPreloadedPreview] = useState(false);

  const [expanded, setExpanded] = useState<Record<number, boolean>>({});
  const [dragIndex, setDragIndex] = useState<number | null>(null);

  useEffect(() => {
    let mounted = true;
    const load = async () => {
      setLoadingTemplates(true);
      setError(null);
      try {
        const data = await api.get<CarouselTemplate[]>("/api/carousels/templates");
        if (!mounted) return;
        setTemplates(data);
        const preferred = data.find((item) => item.id === initialTemplateId)?.id || data[0]?.id || "";
        setSelectedTemplateId((prev) => prev || preferred);
        const renderer = data.find((item) => item.id === preferred)?.renderer;
        setConfig(defaultConfig(renderer));
        setExpanded({ 0: true });
      } catch (err) {
        if (!mounted) return;
        const message = err instanceof ApiError ? err.message : "Failed to load templates";
        setError(message);
      } finally {
        if (mounted) setLoadingTemplates(false);
      }
    };
    void load();
    return () => {
      mounted = false;
    };
  }, [initialTemplateId]);



  useEffect(() => {
    if (!initialQueueItemId) return;
    let mounted = true;

    const loadQueueItem = async () => {
      setLoadingQueueItem(true);
      setError(null);
      try {
        const item = await api.get<ContentQueueItem>(`/api/content-queue/${initialQueueItemId}`);
        if (!mounted) return;
        setConfig(item.config);
        setExpanded({ 0: true });
        const renderer = typeof item.config.renderer === "string" ? item.config.renderer : "";
        const match = templates.find((template) => template.renderer === renderer || template.id === renderer);
        if (match) {
          setSelectedTemplateId(match.id);
        }
        const preloadedSlides = (item.slide_urls || [])
          .filter((url): url is string => typeof url === "string" && url.trim().length > 0)
          .map((url, index) => ({
            index: index + 1,
            key: `queue-${item.id}-${index}`,
            url,
          }));
        if (preloadedSlides.length > 0) {
          setRenderResult({
            workspace_id: `queue-${item.id}`,
            slides: preloadedSlides,
            zip: { key: "", url: "" },
          });
          setSavedExport(null);
          setIsPreloadedPreview(true);
          setInfo("Loaded queue item with cached preview. Click Render preview to regenerate current edits.");
        } else {
          setRenderResult(null);
          setSavedExport(null);
          setIsPreloadedPreview(false);
          setInfo("Loaded queue item config for editing.");
        }
      } catch (err) {
        if (!mounted) return;
        setError(err instanceof ApiError ? err.message : "Failed to load queue item.");
      } finally {
        if (mounted) setLoadingQueueItem(false);
      }
    };

    void loadQueueItem();
    return () => {
      mounted = false;
    };
  }, [initialQueueItemId, templates]);
  const selectedTemplate = useMemo(
    () => templates.find((item) => item.id === selectedTemplateId) || null,
    [templates, selectedTemplateId]
  );

  const toggleExpanded = (index: number) => {
    setExpanded((prev) => ({ ...prev, [index]: !prev[index] }));
  };

  const updateSlide = (index: number, patch: Partial<CarouselSlide>) => {
    setConfig((prev) => {
      const slides = [...prev.slides];
      slides[index] = { ...slides[index], ...patch };
      return { ...prev, slides };
    });
  };

  const updateBullets = (index: number, bullets: string[]) => {
    updateSlide(index, { bullets });
  };

  const deleteSlide = (index: number) => {
    setConfig((prev) => {
      const slides = prev.slides.filter((_, i) => i !== index);
      return { ...prev, slides };
    });
  };

  const addSlide = () => {
    setConfig((prev) => ({
      ...prev,
      slides: [...prev.slides, { type: "body", title: "New Slide", text: "", glow: "corners" }],
    }));
  };

  const onSlideImageFile = async (index: number, file: File | null) => {
    if (!file) return;
    try {
      const encoded = await readFileAsBase64(file);
      setReferenceImages((prev) => ({ ...prev, [file.name]: encoded }));
      updateSlide(index, { image: file.name });
      setInfo(`Loaded image: ${file.name}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load image file");
    }
  };

  const onGenerate = async () => {
    if (!selectedTemplateId) {
      setError("Choose a template first");
      return;
    }
    if (!topic.trim()) {
      setError("Enter a topic before generating");
      return;
    }
    setGenerating(true);
    setError(null);
    setInfo(null);
    try {
      const payload = { template_id: selectedTemplateId, topic };
      const response = await api.post<CarouselGenerateResponse>("/api/carousels/generate", payload);
      setConfig(response.config);
      setExpanded({ 0: true });
      setRenderResult(null);
      setSavedExport(null);
      setIsPreloadedPreview(false);
      setInfo(`Generated with ${response.provider_used}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to generate slides");
    } finally {
      setGenerating(false);
    }
  };

  const onRender = async () => {
    if (!selectedTemplateId) {
      setError("Choose a template first");
      return;
    }
    setRendering(true);
    setError(null);
    setInfo(null);
    try {
      const payload = {
        template_id: selectedTemplateId,
        config,
        reference_images: referenceImages,
      };
      const response = await api.post<CarouselRenderResponse>("/api/carousels/render", payload);
      setRenderResult(response);
      setSavedExport(null);
      setIsPreloadedPreview(false);
      setInfo("Render complete");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to render carousel");
    } finally {
      setRendering(false);
    }
  };

  const onSaveToExports = async () => {
    if (!renderResult || !selectedTemplateId || !renderResult.zip?.url) {
      setError("Render a carousel before saving");
      return;
    }
    setSaving(true);
    setError(null);
    setInfo(null);
    try {
      const slideKeys = renderResult.slides.map((item) => item.key);
      const response = await api.post<CarouselExport>("/api/carousels/exports", {
        template_id: selectedTemplateId,
        config,
        workspace_id: renderResult.workspace_id,
        slide_keys: slideKeys,
        zip_key: renderResult.zip.key,
        preview_key: slideKeys[0],
      });
      setSavedExport(response);
      setInfo("Saved to carousel exports");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to save carousel export");
    } finally {
      setSaving(false);
    }
  };

  const onDropSlide = (dropIndex: number) => {
    if (dragIndex === null || dragIndex === dropIndex) return;
    setConfig((prev) => {
      const slides = [...prev.slides];
      const [moved] = slides.splice(dragIndex, 1);
      slides.splice(dropIndex, 0, moved);
      return { ...prev, slides };
    });
    setDragIndex(null);
  };

  return (
    <div className="space-y-4">
      {loadingTemplates || loadingQueueItem ? (
        <Card>
          <p className="text-sm text-[var(--app-muted)]">Loading carousel editor...</p>
        </Card>
      ) : null}

      {error ? <p className="text-sm text-red-700">{error}</p> : null}
      {info ? <p className="text-sm text-emerald-700">{info}</p> : null}

      <div className="grid gap-4 xl:grid-cols-2">
        <Card padding="sm">
          <div className="space-y-3">
            <div className="grid gap-2 md:grid-cols-2">
              <div className="flex flex-col gap-1">
                <label className="text-sm font-medium text-[var(--app-muted)]">Template</label>
                <select
                  className="rounded-lg border border-[var(--app-border)] bg-white px-3 py-2 text-sm text-[var(--app-text)]"
                  value={selectedTemplateId}
                  onChange={(event) => {
                    const id = event.target.value;
                    setSelectedTemplateId(id);
                    const renderer = templates.find((item) => item.id === id)?.renderer;
                    setConfig(defaultConfig(renderer));
                    setExpanded({ 0: true });
                    setReferenceImages({});
                    setRenderResult(null);
                    setSavedExport(null);
                    setIsPreloadedPreview(false);
                  }}
                >
                  {templates.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.name}
                    </option>
                  ))}
                </select>
              </div>
              <Input
                label="Carousel Title"
                className="px-3 py-2"
                value={config.title || ""}
                onChange={(event) => setConfig((prev) => ({ ...prev, title: event.target.value }))}
              />
            </div>

            <div className="space-y-1.5">
              <label className="text-sm font-medium text-[var(--app-muted)]">Topic / Source Text</label>
              <textarea
                value={topic}
                onChange={(event) => setTopic(event.target.value)}
                rows={3}
                placeholder="Enter a topic or paste source text..."
                className="w-full rounded-lg border border-[var(--app-border)] bg-white px-3 py-2 text-sm text-[var(--app-text)] placeholder-[var(--app-subtle)]"
              />
              <Button onClick={onGenerate} loading={generating}>
                Generate slides
              </Button>
            </div>

            <div className="space-y-2">
              {config.slides.map((slide, index) => {
                const isOpen = expanded[index] ?? index === 0;
                const bullets = slide.bullets || [];
                return (
                  <div
                    key={`slide-${index}`}
                    draggable
                    onDragStart={() => setDragIndex(index)}
                    onDragOver={(event) => event.preventDefault()}
                    onDrop={() => onDropSlide(index)}
                    className="rounded-lg border border-[var(--app-border)] bg-[var(--app-surface-soft)] p-2.5"
                  >
                    <div className="mb-1.5 flex items-center justify-between gap-2">
                      <button
                        type="button"
                        onClick={() => toggleExpanded(index)}
                        className="text-left text-sm font-semibold text-[var(--app-text)]"
                      >
                        Slide {index + 1} · {String(slide.type || "body").toUpperCase()}
                      </button>
                      <div className="flex items-center gap-2">
                        <span className="cursor-grab text-xs text-[var(--app-subtle)]">drag</span>
                        <button
                          type="button"
                          onClick={() => deleteSlide(index)}
                          className="text-xs text-red-700 hover:text-red-800"
                        >
                          Delete
                        </button>
                      </div>
                    </div>

                    {isOpen ? (
                      <div className="space-y-1.5">
                        <div className="grid gap-1.5 md:grid-cols-2">
                          <div className="flex flex-col gap-1">
                            <label className="text-xs font-medium uppercase tracking-wide text-[var(--app-muted)]">
                              Type
                            </label>
                            <select
                              className="rounded-md border border-[var(--app-border)] bg-white px-2 py-1.5 text-xs"
                              value={slide.type || "body"}
                              onChange={(event) =>
                                updateSlide(index, { type: event.target.value as CarouselSlide["type"] })
                              }
                            >
                              <option value="hook">hook</option>
                              <option value="body">body</option>
                              <option value="cta">cta</option>
                            </select>
                          </div>
                          <div className="flex flex-col gap-1">
                            <label className="text-xs font-medium uppercase tracking-wide text-[var(--app-muted)]">
                              Glow
                            </label>
                            <select
                              className="rounded-md border border-[var(--app-border)] bg-white px-2 py-1.5 text-xs"
                              value={String(slide.glow || "corners")}
                              onChange={(event) => updateSlide(index, { glow: event.target.value })}
                            >
                              {GLOW_OPTIONS.map((option) => (
                                <option key={option} value={option}>
                                  {option}
                                </option>
                              ))}
                            </select>
                          </div>
                        </div>

                        <Input
                          label="Title"
                          className="px-2.5 py-1.5 text-xs"
                          value={String(slide.title || "")}
                          onChange={(event) => updateSlide(index, { title: event.target.value })}
                        />
                        <div className="flex flex-col gap-1">
                          <label className="text-sm font-medium text-[var(--app-muted)]">Text</label>
                          <textarea
                            rows={2}
                            value={String(slide.text || "")}
                            onChange={(event) => updateSlide(index, { text: event.target.value })}
                            className="w-full rounded-lg border border-[var(--app-border)] bg-white px-2.5 py-1.5 text-xs"
                          />
                        </div>
                        <Input
                          label="Subtitle"
                          className="px-2.5 py-1.5 text-xs"
                          value={String(slide.subtitle || "")}
                          onChange={(event) => updateSlide(index, { subtitle: event.target.value })}
                        />
                        <Input
                          label="CTA Action"
                          className="px-2.5 py-1.5 text-xs"
                          value={String(slide.cta_action || "")}
                          onChange={(event) => updateSlide(index, { cta_action: event.target.value })}
                        />

                        <div className="space-y-2">
                          <p className="text-xs font-medium uppercase tracking-wide text-[var(--app-muted)]">Bullets</p>
                          {bullets.map((bullet, bulletIndex) => (
                            <div key={`bullet-${index}-${bulletIndex}`} className="flex items-center gap-2">
                              <input
                                value={bullet}
                                onChange={(event) => {
                                  const next = [...bullets];
                                  next[bulletIndex] = event.target.value;
                                  updateBullets(index, next);
                                }}
                                className="w-full rounded-md border border-[var(--app-border)] bg-white px-2 py-1.5 text-xs"
                              />
                              <button
                                type="button"
                                onClick={() => {
                                  const next = bullets.filter((_, i) => i !== bulletIndex);
                                  updateBullets(index, next);
                                }}
                                className="text-xs text-red-700"
                              >
                                Remove
                              </button>
                            </div>
                          ))}
                          <button
                            type="button"
                            onClick={() => updateBullets(index, [...bullets, ""])}
                            className="text-xs text-[#1D3FD0]"
                          >
                            + Add bullet
                          </button>
                        </div>

                        <Input
                          label="Image path / filename"
                          className="px-2.5 py-1.5 text-xs"
                          value={String(slide.image || "")}
                          onChange={(event) => updateSlide(index, { image: event.target.value })}
                          placeholder="asset:headshot.jpg or uploaded-file.png"
                        />
                        <div className="flex flex-col gap-1">
                          <label className="text-xs font-medium uppercase tracking-wide text-[var(--app-muted)]">
                            Upload image file
                          </label>
                          <input
                            type="file"
                            accept="image/*"
                            onChange={(event) => void onSlideImageFile(index, event.target.files?.[0] || null)}
                            className="rounded-md border border-[var(--app-border)] bg-white px-2 py-2 text-xs"
                          />
                        </div>
                      </div>
                    ) : null}
                  </div>
                );
              })}

              <button type="button" onClick={addSlide} className="text-sm text-[#1D3FD0] hover:text-[#1633B8]">
                + Add slide
              </button>
            </div>
          </div>
        </Card>

        <Card>
          <div className="space-y-4">
            <div>
              <h3 className="text-lg font-semibold text-[var(--app-text)]">Preview</h3>
              <p className="mt-1 text-sm text-[var(--app-muted)]">
                {selectedTemplate
                  ? `${selectedTemplate.name} renderer`
                  : "Choose a template and render to preview"}
              </p>
            </div>

            <div className="flex flex-wrap gap-2">
              <Button onClick={onRender} loading={rendering}>
                Render preview
              </Button>
              {renderResult?.zip?.url ? (
                <a
                  href={renderResult.zip.url}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center justify-center rounded-lg border border-[var(--app-border)] px-4 py-2 text-sm text-[var(--app-text)] hover:bg-[var(--app-surface-soft)]"
                >
                  Download all
                </a>
              ) : null}
              <Button
                variant="secondary"
                onClick={onSaveToExports}
                loading={saving}
                disabled={!renderResult?.zip?.url}
              >
                Save to Exports
              </Button>
            </div>
            {isPreloadedPreview ? (
              <p className="text-xs text-[var(--app-subtle)]">
                Preview loaded from queue cache. Click Render preview to regenerate before saving to exports.
              </p>
            ) : null}

            {savedExport ? (
              <p className="text-xs text-emerald-700">
                Saved export: {savedExport.title || "Untitled"} ({savedExport.slide_count} slides)
              </p>
            ) : null}

            <SlidePreview result={renderResult} />
          </div>
        </Card>
      </div>
    </div>
  );
}
