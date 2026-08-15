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
    <Card className="mt-6 border-[#d8cdfb] bg-[#fbfaff] p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[#7054c6]">Live clipping</p>
          <h2 className="mt-1 text-lg font-semibold text-[var(--app-text)]">Twitch channels</h2>
          <p className="mt-1 text-sm text-[var(--app-text-muted)]">Connect channels you manage, then clip them while they are live.</p>
        </div>
        <form onSubmit={connect} className="flex gap-2">
          <input value={login} onChange={(event) => setLogin(event.target.value)} placeholder="Twitch username" className="w-40 rounded-md border border-[var(--app-border)] bg-white px-3 py-2 text-sm" />
          <button type="submit" disabled={connecting} className="rounded-md bg-[#24104f] px-3 py-2 text-sm font-semibold text-white disabled:opacity-50">{connecting ? "Connecting..." : "Connect"}</button>
        </form>
      </div>
      {notice && <p className="mt-4 rounded-md bg-emerald-50 px-3 py-2 text-sm text-emerald-800">{notice}</p>}
      {error && <p className="mt-4 rounded-md bg-red-50 px-3 py-2 text-sm text-red-800">{error}</p>}
      <div className="mt-4 space-y-2">
        {!loading && channels.length === 0 && <p className="text-sm text-[var(--app-text-muted)]">No Twitch channels connected yet.</p>}
        {channels.map((channel) => (
          <div key={channel.id} className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-[#e7e1f7] bg-white px-3 py-3">
            <div><p className="font-medium text-[var(--app-text)]">{channel.display_name}</p><p className="text-xs text-[var(--app-text-muted)]">@{channel.twitch_login}</p></div>
            <div className="flex items-center gap-3"><span className={`rounded-full px-2 py-1 text-xs font-semibold ${channel.is_live ? "bg-rose-100 text-rose-700" : "bg-slate-100 text-slate-600"}`}>{channel.is_live ? "LIVE" : "Offline"}</span><button onClick={() => void clipNow(channel)} disabled={!channel.is_live || clippingId === channel.id} className="rounded-md bg-[#ef4d7b] px-3 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-45">{clippingId === channel.id ? "Requesting..." : "Clip Now"}</button></div>
          </div>
        ))}
      </div>
    </Card>
  );
}
