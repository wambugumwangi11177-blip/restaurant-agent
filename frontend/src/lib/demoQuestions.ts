// Prompted questions for the Demo Restaurant OS, in the words an owner would use.
// Each question carries the area it belongs to, so the answer never depends on a
// "focus area" picker. Every one can be answered from the demo scenario.
export type DemoQuestionArea = { label: string; note: string; slug: string; questions: string[] };
export type DemoQuestionSection = { id: string; title: string; areas: DemoQuestionArea[] };

export const DEMO_STARTERS: { text: string; topic?: string }[] = [
  { text: "Where can I save money?", topic: "intelligence" },
  { text: "What should I expect next week?", topic: "revenue" },
  { text: "What am I about to run out of?", topic: "stock" },
  { text: "How can I improve my menu margins?", topic: "menu" },
  { text: "What needs my attention today?", topic: "notifications" },
  { text: "Is my staff overtime too high?", topic: "team" },
];

export const DEMO_QUESTION_SECTIONS: DemoQuestionSection[] = [
  {
    id: "health",
    title: "How the restaurant is doing",
    areas: [
      { label: "Sales", note: "Money coming in, and what to expect", slug: "revenue", questions: ["How are my sales this week?", "Why is Monday so quiet?", "What should I expect next week?"] },
      { label: "Orders", note: "What guests are ordering right now", slug: "orders", questions: ["Are any orders running late?", "Which way do guests order most?"] },
      { label: "Kitchen", note: "How fast food is coming out", slug: "kitchen", questions: ["Where is the kitchen slowing down?", "What should I fix before the dinner rush?"] },
      { label: "Stock", note: "What is on the shelf and what to order", slug: "stock", questions: ["What am I about to run out of?", "Which ingredients should I use first?", "Will I have enough beef for the week?"] },
      { label: "Bookings", note: "Who is coming tonight", slug: "bookings", questions: ["Who is booked tonight?", "Which bookings still need a reply?"] },
      { label: "Team", note: "Who is working, and the cost", slug: "team", questions: ["Is my staff overtime too high?", "Is dinner properly staffed?"] },
    ],
  },
  {
    id: "money",
    title: "Money and buying",
    areas: [
      { label: "Menu and prices", note: "What earns you the most", slug: "menu", questions: ["Which dish earns me the most?", "Should I raise the price of pilau?", "How can I improve my menu margins?"] },
      { label: "Money left", note: "What is left after costs", slug: "finance", questions: ["How much is left after all my costs?"] },
      { label: "Costs", note: "What it costs to run the place", slug: "expenses", questions: ["What costs me the most?"] },
      { label: "Suppliers", note: "Who supplies you and how reliable they are", slug: "suppliers", questions: ["Is any supplier late?", "Which supplier raised their prices?"] },
      { label: "Buying orders", note: "What you have ordered", slug: "purchasing", questions: ["What orders are waiting for me?"] },
      { label: "Cash and M-Pesa", note: "Does the money match the sales", slug: "cash-reconciliation", questions: ["Does my money match my sales?"] },
    ],
  },
  {
    id: "growth",
    title: "Growing and staying safe",
    areas: [
      { label: "How guests order", note: "Dine-in, takeaway and delivery", slug: "pos", questions: ["How are guests ordering?"] },
      { label: "Marketing", note: "Bringing guests in and back", slug: "marketing", questions: ["What offer could bring guests back?"] },
      { label: "Unusual activity", note: "Things worth a second look", slug: "risk", questions: ["Is there anything unusual I should check?"] },
      { label: "Alerts", note: "Everything asking for your attention", slug: "notifications", questions: ["What needs my attention today?"] },
    ],
  },
  {
    id: "setup",
    title: "Understanding your numbers",
    areas: [
      { label: "Ideas", note: "The few decisions that matter most", slug: "intelligence", questions: ["Where can I save money?", "What are the biggest chances I have this week?"] },
      { label: "Where the numbers come from", note: "How far to trust them", slug: "data-trust", questions: ["Where do these numbers come from?"] },
      { label: "Decisions made", note: "A record of what was suggested", slug: "audit", questions: ["What decisions have been made?"] },
      { label: "Setup", note: "How your restaurant is set up", slug: "settings", questions: ["How is my restaurant set up?"] },
    ],
  },
];
