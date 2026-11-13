import api from "@/lib/api";

export type SetupAnswerChoice = {
  value: string;
  label?: string;
  opens: string | null;
  unlocks: string | null;
  delegate?: boolean;
};

export type SetupQuestion = {
  id: string;
  prompt: string;
  kind?: string;
  brings?: string[];
  arrivals?: { value: string; label: string }[];
  answers: SetupAnswerChoice[];
};

export type StockFollowup = {
  status: "waiting_on_pos" | "count_when_live" | "unknown" | string;
  label: string;
  pending: string | null;
};

export type SetupStep = {
  id: string;
  title: string;
  state: "open" | "done" | "locked";
  unlocks: string;
  locked_reason: string | null;
  completed_at: string | null;
  runnable?: boolean;
  questions?: SetupQuestion[];
};

export type GivenAnswer = {
  question_id: string;
  value: string;
  label: string;
  opens: string | null;
  unlocks: string | null;
  delegated: boolean;
};

export type SetupPayload = {
  must_change_password: boolean;
  has_pin: boolean;
  app_unlocked: boolean;
  unlocked_modules?: string[];
  answers?: GivenAnswer[];
  stock_followup?: StockFollowup | null;
  recipe_gap?: { dish_count: number; missing_count: number; missing_names: string[] };
  steps: SetupStep[];
};

export async function loadSetup(): Promise<SetupPayload> {
  const response = await api.get("/api/v1/staff-setup");
  return response.data as SetupPayload;
}

export function stepById(payload: SetupPayload | null, id: string): SetupStep | undefined {
  return payload?.steps.find((step) => step.id === id);
}

export function hasModule(payload: SetupPayload | null, module: string): boolean {
  return Boolean(payload?.unlocked_modules?.includes(module));
}
