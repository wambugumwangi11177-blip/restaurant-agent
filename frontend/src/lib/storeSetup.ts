import api from "@/lib/api";

export type SetupQuestion = {
  id: string;
  prompt: string;
  answers: { value: string; opens: string | null; unlocks: string | null }[];
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

export type SetupPayload = {
  must_change_password: boolean;
  has_pin: boolean;
  app_unlocked: boolean;
  steps: SetupStep[];
};

export async function loadSetup(): Promise<SetupPayload> {
  const response = await api.get("/api/v1/staff-setup");
  return response.data as SetupPayload;
}

export function stepById(payload: SetupPayload | null, id: string): SetupStep | undefined {
  return payload?.steps.find((step) => step.id === id);
}
