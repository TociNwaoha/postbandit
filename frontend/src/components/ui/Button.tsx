"use client";

import { ButtonHTMLAttributes, forwardRef } from "react";
import { LoadingSpinner } from "./LoadingSpinner";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "sm" | "md" | "lg";
  loading?: boolean;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ variant = "primary", size = "md", loading = false, disabled, children, className = "", ...props }, ref) => {
    const baseStyles = "inline-flex items-center justify-center gap-2 font-medium rounded-lg transition-all focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-offset-[#F4F8FF] disabled:opacity-50 disabled:cursor-not-allowed";

    const variants = {
      primary: "bg-[var(--app-primary)] hover:bg-[var(--app-primary-hover)] text-white focus:ring-[var(--app-primary)]",
      secondary: "bg-white hover:bg-[#F4F8FF] text-[var(--app-text)] border border-[var(--app-border)] focus:ring-[var(--app-border)]",
      ghost: "bg-transparent hover:bg-[#F4F8FF] text-[var(--app-muted)] hover:text-[var(--app-text)] focus:ring-[var(--app-border)]",
      danger: "bg-red-600 hover:bg-red-700 text-white focus:ring-red-500",
    };

    const sizes = {
      sm: "px-3 py-1.5 text-sm",
      md: "px-4 py-2 text-sm",
      lg: "px-6 py-3 text-base",
    };

    return (
      <button
        ref={ref}
        disabled={disabled || loading}
        className={`${baseStyles} ${variants[variant]} ${sizes[size]} ${className}`}
        {...props}
      >
        {loading && <LoadingSpinner size="sm" />}
        {children}
      </button>
    );
  }
);

Button.displayName = "Button";
