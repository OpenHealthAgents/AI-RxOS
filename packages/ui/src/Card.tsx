import * as React from "react";

export interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  title?: string;
}

export function Card({ title, className, children, ...props }: CardProps) {
  const classes = ["rxos-card", className].filter(Boolean).join(" ");
  return (
    <div className={classes} {...props}>
      {title ? <h3 className="rxos-card-title">{title}</h3> : null}
      <div className="rxos-card-body">{children}</div>
    </div>
  );
}
