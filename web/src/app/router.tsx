import { Outlet, Route, Routes } from "react-router-dom";

import { AppShell } from "./app-shell";
import { DemoPage, HomePage, NotFoundPage, RunPage } from "./pages";

function AppShellLayout() {
  return (
    <AppShell>
      <Outlet />
    </AppShell>
  );
}

/** Routes only (no router), so tests can mount them inside a MemoryRouter. */
export function AppRoutes() {
  return (
    <Routes>
      <Route element={<AppShellLayout />}>
        <Route index element={<HomePage />} />
        <Route path="runs/:runId" element={<RunPage />} />
        <Route path="demo" element={<DemoPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
