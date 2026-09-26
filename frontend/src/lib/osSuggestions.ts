import { VIBANDA_AREA_SECTIONS } from "@/lib/vibandaAreas";

export type OSQuestionPurpose = "capability" | "general" | "analysis";
export type OSQuestion = { text: string; purpose: OSQuestionPurpose; needsConnectedData: boolean; availability: "available" | "planned" };
export type OSAreaQuestions = { slug: string; label: string; note: string; questions: OSQuestion[] };

const DATA_QUESTIONS: Record<string, string[]> = {
  Profit: ["Why did my profit change?", "Where am I losing money?", "What are my biggest profit leaks?", "Which items make me the most profit?", "Which items are below my margin target?"],
  Sales: ["Why are my sales changing?", "What are my best-selling items?", "When do I make the most sales?", "Which days are slow?", "How are my sales today?", "How are my sales this week?"],
  Menu: ["Which items make me the most money?", "Which items aren't selling?", "What should I promote?", "Which menu items should I remove?", "Which dishes are worth keeping?", "Which items sell the most?"],
  Prices: ["Which prices should I change?", "Are my prices covering my costs?", "Which items could take a price increase?", "Which items are underpriced?", "How do my prices compare with my costs?"],
  Stock: ["What will run out soon?", "What am I wasting?", "What should I reorder?", "Which ingredients are at risk of expiring?", "What are we about to run out of?"],
  Kitchen: ["What's slowing my kitchen down?", "Which items take too long to prepare?", "When is my kitchen busiest?", "What's happening in my kitchen right now?", "How backed up is the kitchen?", "Which station is the bottleneck?"],
  Orders: ["Which orders are taking too long?", "Where are orders getting stuck?", "How often are orders being cancelled?", "How many orders do I have right now?", "Are there any stuck orders?"],
  Bookings: ["How many customers are expected today?", "How often are customers not showing up?", "When are my busiest booking periods?", "How many bookings do I have today?", "What's my no-show rate?"],
  Staff: ["Where am I overstaffed?", "How is labor affecting my profit?", "Who is working today?", "Does today's staffing match expected demand?", "Am I understaffed today?"],
  Purchasing: ["Which suppliers are costing me more?", "Which supplier is most reliable?", "What purchases are overdue?", "Where can I reduce purchasing costs?", "What do I need to purchase?"],
  "My Business": ["How is my restaurant performing?", "What's changed recently?", "What's going well?", "What should I focus on today?", "Give me a quick health check on my restaurant."],
  Future: ["What's likely to happen next?", "What should I prepare for next week?", "What will my sales look like next week?", "What stock will I run out of?", "Which risks should I plan for?"],
  General: ["What should I be worried about?", "What's the one thing I should know today?", "What happened yesterday?", "Tell me everything important about my restaurant."],
};

const SOURCE_GROUPS: Record<string, string[]> = {
  revenue: ["Sales", "Profit"], orders: ["Orders", "Sales"], kitchen: ["Kitchen", "Orders"],
  stock: ["Stock"], bookings: ["Bookings"], team: ["Staff"], menu: ["Menu", "Prices", "Profit"],
  finance: ["Profit", "My Business"], expenses: ["Profit"], suppliers: ["Purchasing", "Stock"],
  purchasing: ["Purchasing", "Stock"], "cash-reconciliation": ["Profit", "My Business"],
  pos: ["Orders", "Sales"], marketing: ["Sales", "My Business"], risk: ["General", "Future"],
  notifications: ["General", "My Business"], intelligence: ["My Business", "Future", "General"],
  "data-trust": ["General", "Future"], audit: ["General"], settings: ["General"],
};

// These topics have implemented, question-specific analysis handlers today.
// Other Home areas stay discoverable, but do not imply that their analysis is live.
const LIVE_ANALYSIS_AREAS = new Set(["revenue", "orders", "kitchen", "stock", "bookings", "team", "menu"]);

const PLANNED_DATA_QUESTIONS: Record<string, string[]> = {
  suppliers: ["Which suppliers are costing me more?", "Which supplier is most reliable?", "What purchases are overdue?", "Where can I reduce purchasing costs?", "What do I need to purchase?"],
  purchasing: ["Which suppliers are costing me more?", "Which supplier is most reliable?", "What purchases are overdue?", "Where can I reduce purchasing costs?", "What do I need to purchase?"],
  "cash-reconciliation": ["How much cash, M-Pesa, and card revenue is unmatched?", "Which settlement needs review?"],
  pos: ["Which sales channels are growing?", "How are till transactions changing?"],
  marketing: ["Which guest campaign is working?", "How many guests are returning?"],
  risk: ["Are there unusual refunds or voids?", "Which control risks need review?"],
  notifications: ["What important changes need my attention?", "Which reminders are still open?"],
  intelligence: ["What should I focus on today?", "Which business risks should I prepare for?"],
  "data-trust": ["When did restaurant data last arrive?", "Is the connected data complete enough to use?"],
  audit: ["What business changes need review?", "Which decisions were recorded?"],
  settings: ["Which services are connected?", "What restaurant settings can I manage?"],
};

export const OS_AREA_QUESTIONS: OSAreaQuestions[] = VIBANDA_AREA_SECTIONS.flatMap((section) =>
  section.areas.map(([label, note, slug]) => {
    const available = LIVE_ANALYSIS_AREAS.has(slug);
    const questions: OSQuestion[] = [
      { text: `What does the ${label} page help me understand?`, purpose: "capability", needsConnectedData: false, availability: available ? "available" : "planned" },
      { text: `Help me think through an improvement to ${label.toLowerCase()}.`, purpose: "general", needsConnectedData: false, availability: "available" },
      ...(SOURCE_GROUPS[slug] ?? []).flatMap((group) => (DATA_QUESTIONS[group] ?? []).map((text) => ({
        text, purpose: "analysis" as const, needsConnectedData: true, availability: available ? "available" as const : "planned" as const,
      }))),
      ...(PLANNED_DATA_QUESTIONS[slug] ?? []).map((text) => ({
        text, purpose: "analysis" as const, needsConnectedData: true, availability: "planned" as const,
      })),
    ];
    return { slug, label, note, questions: [...new Map(questions.map((question) => [question.text, question])).values()] };
  }),
);
