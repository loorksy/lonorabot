import type { ReactNode } from "react";

/** The agent pages' styles apply inside .ag-scope (display: contents): pages and the
 * sheets they open, which render outside the page. */
export const scoped = (node: ReactNode) => <div className="ag-scope">{node}</div>;
