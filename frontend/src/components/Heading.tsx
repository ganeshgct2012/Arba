import { type ReactNode } from "react";

export function Heading({ title, subtitle, actions }: { title: string; subtitle: string; actions?: ReactNode }) {
  return <div className="page-heading"><div><h1>{title}</h1><p>{subtitle}</p></div><div className="heading-actions">{actions}</div></div>;
}

