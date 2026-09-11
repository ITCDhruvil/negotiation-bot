"use client";

import { cn } from "@/lib/utils";

export interface LoaderProps {
  variant?:
    | "circular"
    | "classic"
    | "pulse"
    | "pulse-dot"
    | "dots"
    | "typing"
    | "wave"
    | "bars"
    | "terminal"
    | "text-blink"
    | "text-shimmer"
    | "loading-dots";
  size?: "sm" | "md" | "lg";
  text?: string;
  className?: string;
}

export function TypingLoader({
  className,
  size = "md",
}: {
  className?: string;
  size?: "sm" | "md" | "lg";
}) {
  const dotSizes = {
    sm: "h-1 w-1",
    md: "h-1.5 w-1.5",
    lg: "h-2 w-2",
  };
  const containerSizes = {
    sm: "h-4",
    md: "h-5",
    lg: "h-6",
  };

  return (
    <div
      className={cn("flex items-center space-x-1", containerSizes[size], className)}
      role="status"
      aria-label="Aria is typing"
    >
      {[0, 1, 2].map((i) => (
        <div
          key={i}
          className={cn("animate-[typing_1s_infinite] rounded-full bg-ink", dotSizes[size])}
          style={{ animationDelay: `${i * 250}ms` }}
        />
      ))}
      <span className="sr-only">Loading</span>
    </div>
  );
}

export function Loader({ variant = "typing", size = "md", className }: LoaderProps) {
  void variant;
  return <TypingLoader size={size} className={className} />;
}
