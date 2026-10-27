import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";

const NAV_CLASS = ({ isActive }: { isActive: boolean }): string =>
  isActive ? "text-accent underline underline-offset-4" : "text-muted hover:text-fg";

export interface AppShellProps {
  children: ReactNode;
}

/**
 * Application shell: skip link, header (56 px), primary navigation, main region.
 * Layout and type come from docs/03_UI_Spec.md §3/§5; colours come from tokens.css.
 */
export function AppShell({ children }: AppShellProps) {
  return (
    <div className="flex min-h-screen flex-col bg-bg font-ui text-fg">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-10 focus:rounded-control focus:bg-surface focus:px-4 focus:py-2"
      >
        Skip to content
      </a>

      <header className="border-b border-border">
        <div className="mx-auto flex h-14 max-w-page items-center gap-6 px-6">
          <h1 className="m-0 text-h3 font-semibold">Process Watcher</h1>
          <nav aria-label="Primary" className="flex gap-4 text-small">
            <NavLink to="/" end className={NAV_CLASS}>
              Check a procedure
            </NavLink>
            <NavLink to="/demo" className={NAV_CLASS}>
              Demo
            </NavLink>
          </nav>
          <p className="m-0 ml-auto hidden text-small text-muted md:block">
            Not what the paperwork says: what actually happened.
          </p>
        </div>
      </header>

      <main id="main" className="mx-auto w-full max-w-page flex-1 px-6 py-8">
        {children}
      </main>

      <footer className="border-t border-border px-6 py-4 text-small text-muted">
        <div className="mx-auto max-w-page">
          Evidence is always a real frame; AI illustrations are watermarked and never evidence.
        </div>
      </footer>
    </div>
  );
}
