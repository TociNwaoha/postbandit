import { HTMLAttributes } from "react";

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  padding?: "sm" | "md" | "lg";
}

export function Card({ padding = "md", className = "", children, ...props }: CardProps) {
  const paddings = { sm: "p-4", md: "p-6", lg: "p-8" };

  return (
    <div
      className={`bg-white border border-[var(--app-border)] rounded-xl shadow-[0_1px_2px_rgba(9,21,40,0.04)] ${paddings[padding]} ${className}`}
      {...props}
    >
      {children}
    </div>
  );
}
