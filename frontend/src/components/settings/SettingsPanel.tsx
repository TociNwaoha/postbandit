"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { signOut } from "next-auth/react";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { api, ApiError } from "@/lib/api";
import { User } from "@/types";

interface MessageResponse {
  message: string;
}

interface UpdateEmailResponse {
  message: string;
  user: User;
}

export function SettingsPanel() {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [emailDraft, setEmailDraft] = useState("");
  const [emailPassword, setEmailPassword] = useState("");
  const [emailError, setEmailError] = useState<string | null>(null);
  const [emailSaving, setEmailSaving] = useState(false);

  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [passwordSaving, setPasswordSaving] = useState(false);

  const [deletePassword, setDeletePassword] = useState("");
  const [deleteConfirmText, setDeleteConfirmText] = useState("");
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);

  const createdAtLabel = useMemo(() => {
    if (!user?.created_at) return "Unknown";
    const date = new Date(user.created_at);
    if (Number.isNaN(date.getTime())) return "Unknown";
    return date.toLocaleString();
  }, [user?.created_at]);

  const loadUser = async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const current = await api.get<User>("/api/auth/me");
      setUser(current);
      setEmailDraft(current.email || "");
    } catch (err) {
      setLoadError(err instanceof ApiError ? err.message : "Failed to load settings");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadUser();
  }, []);

  const handleEmailSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!user) return;
    setEmailError(null);

    if (!emailDraft.trim()) {
      setEmailError("Email is required");
      return;
    }
    if (!emailPassword) {
      setEmailError("Current password is required");
      return;
    }

    setEmailSaving(true);
    try {
      const response = await api.patch<UpdateEmailResponse>("/api/auth/me/email", {
        new_email: emailDraft.trim().toLowerCase(),
        current_password: emailPassword,
      });
      setUser(response.user);
      await signOut({ callbackUrl: "/login?settings=email-updated" });
    } catch (err) {
      setEmailError(err instanceof ApiError ? err.message : "Failed to update email");
    } finally {
      setEmailSaving(false);
    }
  };

  const handlePasswordSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setPasswordError(null);

    if (!currentPassword || !newPassword || !confirmPassword) {
      setPasswordError("All password fields are required");
      return;
    }
    if (newPassword.length < 8) {
      setPasswordError("New password must be at least 8 characters");
      return;
    }
    if (newPassword !== confirmPassword) {
      setPasswordError("New password and confirmation do not match");
      return;
    }

    setPasswordSaving(true);
    try {
      await api.post<MessageResponse>("/api/auth/me/password", {
        current_password: currentPassword,
        new_password: newPassword,
      });
      await signOut({ callbackUrl: "/login?settings=password-updated" });
    } catch (err) {
      setPasswordError(err instanceof ApiError ? err.message : "Failed to update password");
    } finally {
      setPasswordSaving(false);
    }
  };

  const handleDeleteSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setDeleteError(null);

    if (!deletePassword) {
      setDeleteError("Current password is required");
      return;
    }
    if (deleteConfirmText !== "DELETE") {
      setDeleteError("Type DELETE to confirm account deletion");
      return;
    }

    setDeleting(true);
    try {
      await api.post<void>("/api/auth/me/delete", {
        current_password: deletePassword,
        confirm_text: deleteConfirmText,
      });
      await signOut({ callbackUrl: "/signup?account=deleted" });
    } catch (err) {
      setDeleteError(err instanceof ApiError ? err.message : "Failed to delete account");
    } finally {
      setDeleting(false);
    }
  };

  if (loading) {
    return <p className="text-sm text-[var(--app-muted)]">Loading settings...</p>;
  }

  if (loadError) {
    return <p className="text-sm text-red-700">{loadError}</p>;
  }

  if (!user) {
    return <p className="text-sm text-red-700">Failed to load account settings</p>;
  }

  return (
    <div className="space-y-5">
      <Card>
        <h3 className="text-base font-semibold text-[var(--app-text)]">Account</h3>
        <p className="mt-1 text-xs text-[var(--app-muted)]">Update your sign-in email address.</p>

        <form className="mt-4 space-y-3" onSubmit={handleEmailSubmit}>
          <Input
            label="Email"
            type="email"
            value={emailDraft}
            onChange={(event) => setEmailDraft(event.target.value)}
            autoComplete="email"
            required
          />
          <Input
            label="Current Password"
            type="password"
            value={emailPassword}
            onChange={(event) => setEmailPassword(event.target.value)}
            autoComplete="current-password"
            required
          />
          <div className="grid gap-2 rounded-lg border border-[var(--app-border)] bg-[var(--app-surface-soft)] p-3 text-xs text-[var(--app-muted)] sm:grid-cols-2">
            <p>
              <span className="font-medium text-[var(--app-text)]">Tier:</span> {user.tier}
            </p>
            <p>
              <span className="font-medium text-[var(--app-text)]">Account Created:</span> {createdAtLabel}
            </p>
          </div>
          {emailError ? <p className="text-sm text-red-700">{emailError}</p> : null}
          <div className="flex justify-end">
            <Button type="submit" loading={emailSaving}>
              Save Email
            </Button>
          </div>
        </form>
      </Card>

      <Card>
        <h3 className="text-base font-semibold text-[var(--app-text)]">Plan & Usage</h3>
        <p className="mt-1 text-xs text-[var(--app-muted)]">Billing management coming soon.</p>
        <div className="mt-4 grid gap-2 rounded-lg border border-[var(--app-border)] bg-[var(--app-surface-soft)] p-3 text-sm text-[var(--app-text)] sm:grid-cols-2">
          <p>
            <span className="font-semibold">Current Tier:</span> {user.tier}
          </p>
          <p>
            <span className="font-semibold">Videos Used:</span> {user.videos_used}
          </p>
        </div>
      </Card>

      <Card>
        <h3 className="text-base font-semibold text-[var(--app-text)]">Security</h3>
        <p className="mt-1 text-xs text-[var(--app-muted)]">Change your password. You will be asked to sign in again.</p>

        <form className="mt-4 space-y-3" onSubmit={handlePasswordSubmit}>
          <Input
            label="Current Password"
            type="password"
            value={currentPassword}
            onChange={(event) => setCurrentPassword(event.target.value)}
            autoComplete="current-password"
            required
          />
          <Input
            label="New Password"
            type="password"
            value={newPassword}
            onChange={(event) => setNewPassword(event.target.value)}
            autoComplete="new-password"
            required
          />
          <Input
            label="Confirm New Password"
            type="password"
            value={confirmPassword}
            onChange={(event) => setConfirmPassword(event.target.value)}
            autoComplete="new-password"
            required
          />
          {passwordError ? <p className="text-sm text-red-700">{passwordError}</p> : null}
          <div className="flex justify-end">
            <Button type="submit" loading={passwordSaving}>
              Update Password
            </Button>
          </div>
        </form>
      </Card>

      <Card className="border-red-200">
        <h3 className="text-base font-semibold text-red-700">Danger Zone</h3>
        <p className="mt-1 text-xs text-red-700/90">
          Delete your account and all associated data. This action cannot be undone.
        </p>

        <form className="mt-4 space-y-3" onSubmit={handleDeleteSubmit}>
          <Input
            label="Current Password"
            type="password"
            value={deletePassword}
            onChange={(event) => setDeletePassword(event.target.value)}
            autoComplete="current-password"
            required
          />
          <Input
            label='Type "DELETE" to Confirm'
            type="text"
            value={deleteConfirmText}
            onChange={(event) => setDeleteConfirmText(event.target.value)}
            required
          />
          {deleteError ? <p className="text-sm text-red-700">{deleteError}</p> : null}
          <div className="flex justify-end">
            <Button type="submit" variant="danger" loading={deleting}>
              Delete Account
            </Button>
          </div>
        </form>
      </Card>
    </div>
  );
}
