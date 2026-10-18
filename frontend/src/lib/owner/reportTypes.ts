/** GET /owner/report/{period}: the sections of a report (backend/owner/reports.py, owner/report_sections.py). */
import type { AnswerAssumption, AnswerRow } from "./ask";
import type { Block, BlockState } from "./types";

export type ReportPeriod = "daily" | "weekly" | "monthly" | "yearly";

export type MonthPoint = { month: string; label: string; sales: number; orders: number; partial: boolean };

export type ReportSection = Block & {
  key: string;
  title: string;
  /** The days it covers, in words: "Today", "The last 7 days", "October 2026 so far", "The last 12 months". */
  window: string;
  headline?: string;
  rows: AnswerRow[];
  assumptions: AnswerAssumption[];
  /** describes the report rather than being data in it (the targets used) */
  info?: boolean;
  series?: MonthPoint[];
};

export type OwnerReport = {
  period: ReportPeriod;
  range: string;
  /** monthly only: the month the sections cover, 2026-10 */
  month?: string;
  state: BlockState;
  as_of: string | null;
  sections: ReportSection[];
  read: Block & { text: string | null };
};
