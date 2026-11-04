import type { Report } from "../types/generated/report";

import type { ApiClient } from "./client";

/** One frozen case as listed by `GET /demo/cases`. */
export interface DemoCaseSummary {
  case_id: string;
  title: string;
  description: string;
  source_run: string;
  status?: string;
  deviation_count?: number;
  duration_s?: number;
}

/** One frozen case with the report the review core renders (`GET /demo/cases/{id}`). */
export interface DemoCaseDetail extends DemoCaseSummary {
  duration_s: number;
  deviation_count: number;
  media: { analysis: string };
  report: Report;
}

interface DemoCaseListResponse {
  cases: DemoCaseSummary[];
}

export async function listDemoCases(client: ApiClient): Promise<DemoCaseSummary[]> {
  const payload = await client.get<DemoCaseListResponse>("/demo/cases");
  return payload.cases;
}

export function getDemoCase(client: ApiClient, caseId: string): Promise<DemoCaseDetail> {
  return client.get<DemoCaseDetail>(`/demo/cases/${encodeURIComponent(caseId)}`);
}
