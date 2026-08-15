"use client";

import { FormEvent, useEffect, useState } from "react";

import { Card } from "@/components/ui/Card";
import { api, ApiError } from "@/lib/api";

type TwitchChannel = {
  id: string;
  twitch_login: string;
  display_name: string;
  is_live: boolean;
  status: "active" | "disconnected";
};

type ClipRequest = { video_id: string; task_id: string; status: string; message: string };

export function TwitchConnectCard() {
  const [count, setCount] = useState(0);

  useEffect(() => {
    let mounted = true;
    api.get<TwitchChannel[]>("/api/twitch-channels").then((channels) => {
      if (mounted) setCount(channels.filter((channel) => channel.status === "active").length);
    }).catch(() => undefined);
    return () => { mounted = false; };
  }, []);

  const ready = count > 0;
  return (
    <div className="space-y-1">
      <button type="button" onClick={() => document.getElementById("twitch-channel-login")?.focus()} className="w-full rounded-md bg-[#9146FF] px-3 py-2 text-sm font-semibold text-white transition hover:bg-[#772CE8]">
        <span className="flex items-center justify-between gap-2"><span className="flex items-center gap-2.5"><svg className="h-5 w-5" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M4.2 3 3 6.2v13.1h4.5V21h2.5l1.7-1.7h3.7L21 13.7V3H4.2Zm15 9.8-3.2 3.2h-4.3L10 17.7V16H6.3V4.8h12.9v8Zm-3.3-5.4h-1.8v5.2h1.8V7.4Zm-5 0H9.1v5.2h1.8V7.4Z" /></svg>Connect Twitch</span><span className="rounded-full bg-white/20 px-1.5 py-0.5 text-[10px] leading-none">{count}</span></span>
      </button>
      <p className={`px-1 text-[11px] ${ready ? "text-emerald-700" : "text-[var(--app-muted)]"}`}>{ready ? "Ready" : "Connect a channel to enable live clipping"}</p>
    </div>
  );
}

export function TwitchChannelsPanel() {
  const [channels, setChannels] = useState<TwitchChannel[]>([]);
  const [login, setLogin] = useState("");
  const [loading, setLoading] = useState(true);
  const [connecting, setConnecting] = useState(false);
  const [clippingId, setClippingId] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadChannels = async () => {
    try {
      setChannels(await api.get<TwitchChannel[]>("/api/twitch-channels"));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load Twitch channels");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadChannels();
    const timer = window.setInterval(() => void loadChannels(), 5000);
    return () => window.clearInterval(timer);
  }, []);

  const connect = async (event: FormEvent) => {
    event.preventDefault();
    if (!login.trim()) return;
    setConnecting(true);
    setError(null);
    try {
      const channel = await api.post<TwitchChannel>("/api/twitch-channels", { login });
      setChannels((current) => [channel, ...current.filter((item) => item.id !== channel.id)]);
      setLogin("");
      setNotice(`${channel.display_name} is connected. Live status updates automatically.`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not connect Twitch channel");
    } finally {
      setConnecting(false);
    }
  };

  const clipNow = async (channel: TwitchChannel) => {
    setClippingId(channel.id);
    setError(null);
    setNotice(null);
    try {
      const result = await api.post<ClipRequest>(`/api/twitch-channels/${channel.id}/clip`, {});
      setNotice(`Clip requested for ${channel.display_name}. Processing has started and will appear in Videos shortly.`);
      void result;
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not request Twitch clip");
    } finally {
      setClippingId(null);
    }
  };

  return (
    <Card padding="sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-[var(--app-text)]">Live clipping</h3>
          <p className="mt-1 text-xs text-[var(--app-muted)]">Connect channels you manage, then clip them while they are live.</p>
        </div>
        <form onSubmit={connect} className="flex gap-2">
          <input id="twitch-channel-login" value={login} onChange={(event) => setLogin(event.target.value)} placeholder="Twitch username" className="w-40 rounded-md border border-[var(--app-border)] bg-white px-3 py-2 text-sm" />
          <button type="submit" disabled={connecting} className="rounded-md bg-[var(--app-primary)] px-3 py-2 text-sm font-semibold text-white hover:bg-[var(--app-primary-hover)] disabled:opacity-50">{connecting ? "Connecting..." : "Connect"}</button>
        </form>
      </div>
      {notice && <p className="mt-4 rounded-md bg-emerald-50 px-3 py-2 text-sm text-emerald-800">{notice}</p>}
      {error && <p className="mt-4 rounded-md bg-red-50 px-3 py-2 text-sm text-red-800">{error}</p>}
      <div className="mt-4 space-y-2">
        {!loading && channels.length === 0 && <p className="text-sm text-[var(--app-text-muted)]">No Twitch channels connected yet.</p>}
        {channels.map((channel) => (
          <div key={channel.id} className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-[var(--app-border)] bg-[var(--app-surface-soft)] px-3 py-3">
            <div><p className="font-medium text-[var(--app-text)]">{channel.display_name}</p><p className="text-xs text-[var(--app-text-muted)]">@{channel.twitch_login}</p></div>
            <div className="flex items-center gap-3"><span className={`rounded-full px-2 py-1 text-xs font-semibold ${channel.is_live ? "bg-rose-100 text-rose-700" : "bg-slate-100 text-slate-600"}`}>{channel.is_live ? "LIVE" : "Offline"}</span><button onClick={() => void clipNow(channel)} disabled={!channel.is_live || clippingId === channel.id} className="rounded-md bg-[#ef4d7b] px-3 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-45">{clippingId === channel.id ? "Requesting..." : "Clip Now"}</button></div>
          </div>
        ))}
      </div>
    </Card>
  );
}
