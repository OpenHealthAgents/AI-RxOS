import * as React from "react";

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  tone?: "neutral" | "success" | "warning" | "danger" | "info";
}

const TONE_CLASS: Record<NonNullable<BadgeProps["tone"]>, string> = {
  neutral: "rxos-badge-neutral",
  success: "rxos-badge-success",
  warning: "rxos-badge-warning",
  danger: "rxos-badge-danger",
  info: "rxos-badge-info",
};

export function Badge({ tone = "neutral", className, ...props }: BadgeProps) {
  const classes = ["rxos-badge", TONE_CLASS[tone], className].filter(Boolean).join(" ");
  return <span className={classes} {...props} />;
}
