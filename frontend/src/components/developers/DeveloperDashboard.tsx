"use client";

import { FormEvent, useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { ApiError, api } from "@/lib/api";
import { DeveloperApiKey, DeveloperUsage } from "@/types";

const QUICK_STARTS = {
  curl: `curl -X POST https://api.postbandit.com/api/v1/videos/import \\\n  -H "Authorization: Bearer YOUR_API_KEY" \\\n  -H "Content-Type: application/json" \\\n  -d '{"url":"https://youtube.com/watch?v=..."}'`,
  python: `import requests\n\nresp = requests.post(\n    "https://api.postbandit.com/api/v1/videos/import",\n    headers={"Authorization": "Bearer YOUR_API_KEY"},\n    json={"url": "https://youtube.com/watch?v=..."},\n)\nprint(resp.json())`,
  javascript: `const resp = await fetch("https://api.postbandit.com/api/v1/videos/import", {\n  method: "POST",\n  headers: {\n    Authorization: "Bearer YOUR_API_KEY",\n    "Content-Type": "application/json",\n  },\n  body: JSON.stringify({ url: "https://youtube.com/watch?v=..." }),\n});\nconsole.log(await resp.json());`,
} as const;

type SnippetTab = keyof typeof QUICK_STARTS;

function UsageBar({ label, current, limit, percent }: { label: string; current: number; limit: number; percent: number }) {
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-3 text-sm">
        <span className="font-medium text-[var(--app-text)]">{label}</span>
        <span className="text-[var(--app-muted)]">{current} / {limit} calls ({percent.toFixed(1)}%)</span>
      </div>
      <div className="h-2 rounded-full bg-[var(--app-surface-soft)]">
        <div className="h-2 rounded-full bg-[var(--app-primary)]" style={{ width: `${Math.min(100, percent)}%` }} />
      </div>
    </div>
  );
}

export function DeveloperDashboard() {
  const [keys, setKeys] = useState<DeveloperApiKey[]>([]);
  const [usage, setUsage] = useState<DeveloperUsage | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [keyName, setKeyName] = useState("");
  const [createdKey, setCreatedKey] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<SnippetTab>("curl");
  const keyRef = useRef<HTMLDivElement>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const [nextKeys, nextUsage] = await Promise.all([
        api.get<DeveloperApiKey[]>("/api/developer/keys"),
        api.get<DeveloperUsage>("/api/developer/usage"),
      ]);
      setKeys(nextKeys);
      setUsage(nextUsage);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load developer settings.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const closeModal = () => {
    setCreatedKey(null);
    setKeyName("");
    setModalOpen(false);
  };

  const createKey = async (event: FormEvent) => {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const created = await api.post<DeveloperApiKey & { full_key: string }>("/api/developer/keys", { name: keyName });
      setCreatedKey(created.full_key);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to create API key.");
    } finally {
      setSaving(false);
    }
  };

  const revokeKey = async (keyId: string) => {
    if (!window.confirm("Revoke this API key? Existing integrations using it will stop working.")) return;
    setSaving(true);
    setError(null);
    try {
      await api.delete(`/api/developer/keys/${keyId}`);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to revoke API key.");
    } finally {
      setSaving(false);
    }
  };

  const copyCreatedKey = async () => {
    const text = keyRef.current?.textContent || "";
    if (!text) return;
    await navigator.clipboard.writeText(text);
  };

  return (
    <div className="space-y-6">
      <Card>
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-[var(--app-subtle)]">API Access</p>
            <h2 className="mt-1 text-2xl font-semibold text-[var(--app-text)]">Developer API</h2>
            <p className="mt-1 text-sm text-[var(--app-muted)]">Create API keys for automations, integrations, and external tools.</p>
          </div>
          <span className="rounded-full bg-[rgba(29,63,208,0.1)] px-3 py-1 text-sm font-medium text-[var(--app-primary)]">
            {usage ? `${usage.plan.charAt(0).toUpperCase()}${usage.plan.slice(1)} Plan` : "Loading plan"}
          </span>
        </div>
        {error ? <p className="mt-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p> : null}
        {loading ? <p className="mt-4 text-sm text-[var(--app-muted)]">Loading API access...</p> : null}
        {usage ? (
          <div className="mt-6 grid gap-5 md:grid-cols-2">
            <UsageBar label="Usage this hour" current={usage.usage.this_hour} limit={usage.limits.per_hour} percent={usage.usage.hour_percent} />
            <UsageBar label="Usage today" current={usage.usage.today} limit={usage.limits.per_day} percent={usage.usage.day_percent} />
          </div>
        ) : null}
      </Card>

      <Card>
        <div className="flex items-center justify-between gap-4">
          <div>
            <h3 className="text-lg font-semibold text-[var(--app-text)]">API Keys</h3>
            <p className="text-sm text-[var(--app-muted)]">You can keep up to five active keys.</p>
          </div>
          <Button onClick={() => setModalOpen(true)}>Create new key</Button>
        </div>
        <div className="mt-5 space-y-3">
          {keys.length ? keys.map((item) => (
            <div key={item.id} className="flex flex-col gap-3 rounded-xl border border-[var(--app-border)] p-4 md:flex-row md:items-center md:justify-between">
              <div>
                <p className="font-medium text-[var(--app-text)]">{item.name}</p>
                <p className="font-mono text-sm text-[var(--app-muted)]">{item.key_prefix}</p>
                <p className="text-xs text-[var(--app-subtle)]">Last used: {item.last_used_at ? new Date(item.last_used_at).toLocaleString() : "never"}</p>
              </div>
              <Button variant="ghost" disabled={saving || !item.is_active} onClick={() => revokeKey(item.id)}>
                {item.is_active ? "Revoke" : "Revoked"}
              </Button>
            </div>
          )) : (
            <p className="rounded-xl border border-dashed border-[var(--app-border)] p-5 text-sm text-[var(--app-muted)]">No API keys yet.</p>
          )}
        </div>
      </Card>

      <Card>
        <h3 className="text-lg font-semibold text-[var(--app-text)]">Quick start</h3>
        <div className="mt-4 flex flex-wrap gap-2">
          {(Object.keys(QUICK_STARTS) as SnippetTab[]).map((tab) => (
            <button
              key={tab}
              type="button"
              onClick={() => setActiveTab(tab)}
              className={`rounded-lg px-3 py-1.5 text-sm font-medium ${activeTab === tab ? "bg-[var(--app-primary)] text-white" : "bg-[var(--app-surface-soft)] text-[var(--app-muted)]"}`}
            >
              {tab === "curl" ? "curl" : tab === "python" ? "Python" : "JavaScript"}
            </button>
          ))}
        </div>
        <pre className="mt-4 overflow-x-auto rounded-xl bg-[#091528] p-4 text-sm text-white"><code>{QUICK_STARTS[activeTab]}</code></pre>
      </Card>

      {modalOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-[#091528]/40 p-4">
          <div className="w-full max-w-lg rounded-2xl bg-white p-6 shadow-2xl">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h3 className="text-xl font-semibold text-[var(--app-text)]">Create API key</h3>
                <p className="mt-1 text-sm text-[var(--app-muted)]">The full key is shown once. Store it securely.</p>
              </div>
              <button type="button" onClick={closeModal} className="text-2xl text-[var(--app-subtle)]">×</button>
            </div>
            {createdKey ? (
              <div className="mt-5 space-y-4">
                <p className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-800">This key will only be shown once. Copy it now.</p>
                <div ref={keyRef} className="break-all rounded-xl border border-[var(--app-border)] bg-[var(--app-surface-soft)] p-3 font-mono text-sm text-[var(--app-text)]">
                  {createdKey}
                </div>
                <div className="flex justify-end gap-2">
                  <Button variant="secondary" onClick={copyCreatedKey}>Copy key</Button>
                  <Button onClick={closeModal}>Done</Button>
                </div>
              </div>
            ) : (
              <form className="mt-5 space-y-4" onSubmit={createKey}>
                <Input label="Key name" value={keyName} onChange={(event) => setKeyName(event.target.value)} placeholder="My MCP Key" required />
                <div className="flex justify-end gap-2">
                  <Button type="button" variant="secondary" onClick={closeModal}>Cancel</Button>
                  <Button type="submit" loading={saving}>Create key</Button>
                </div>
              </form>
            )}
          </div>
        </div>
      ) : null}
    </div>
  );
}
