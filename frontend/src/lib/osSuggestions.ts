// The sketch's built-in question groups (restaurant parts). Copied from
// restaurant-os-ai-frontend--wambugumwangi11.replit.app (its ME array),
// 6 per group — ones our backend can actually answer from real data.
export const QUESTION_GROUPS: { name: string; questions: string[] }[] = [
  { name: "Profit", questions: ["Why did my profit change?", "Where am I losing money?", "What are my biggest profit leaks?", "Which items make me the most profit?", "How can I increase my profit?", "Which items are below my margin target?"] },
  { name: "Sales", questions: ["Why are my sales changing?", "What are my best-selling items?", "When do I make the most sales?", "Which days are slow?", "How are my sales today?", "How are my sales this week?"] },
  { name: "Menu", questions: ["Which items make me the most money?", "Which items aren't selling?", "What should I promote?", "Which menu items should I remove?", "Which dishes are worth keeping?", "Which items sell the most?"] },
  { name: "Prices", questions: ["Which prices should I change?", "Are my prices covering my costs?", "Which items could take a price increase?", "Which items are underpriced?", "Should I increase my prices?", "How do my prices compare with my costs?"] },
  { name: "Stock", questions: ["What will run out soon?", "What am I wasting?", "What should I reorder?", "Which ingredients are at risk of expiring?", "How can I reduce food waste this week?", "What are we about to run out of?"] },
  { name: "Kitchen", questions: ["What's slowing my kitchen down?", "Which items take too long to prepare?", "When is my kitchen busiest?", "What's happening in my kitchen right now?", "How backed up is the kitchen?", "Which station is the bottleneck?"] },
  { name: "Orders", questions: ["Which orders are taking too long?", "Where are orders getting stuck?", "How often are orders being cancelled?", "How many orders do I have right now?", "Are there any stuck orders?", "How many delivery orders do I have?"] },
  { name: "Bookings", questions: ["How many customers are expected today?", "How often are customers not showing up?", "How much money am I losing from no-shows?", "When are my busiest booking periods?", "How many bookings do I have today?", "What's my no-show rate?"] },
  { name: "Staff", questions: ["Where am I overstaffed?", "How is labor affecting my profit?", "Who is working today?", "Does today's staffing match expected demand?", "Am I understaffed today?", "How is staff productivity changing?"] },
  { name: "Purchasing", questions: ["Which suppliers are costing me more?", "Which supplier is most reliable?", "What purchases are overdue?", "Where can I reduce purchasing costs?", "What do I need to purchase?", "Which deliveries are overdue?"] },
  { name: "My Business", questions: ["How is my restaurant performing?", "What's changed recently?", "What's going well?", "What should I focus on today?", "Give me a quick health check on my restaurant.", "What's my biggest opportunity?"] },
  { name: "Future", questions: ["What's likely to happen next?", "What should I prepare for next week?", "What will my sales look like next week?", "What stock will I run out of?", "What could affect next month's profit?", "Which risks should I plan for?"] },
  { name: "General", questions: ["What should I be worried about?", "What's the one thing I should know today?", "What happened yesterday?", "Can you explain this in simple terms?", "Where should I start?", "Tell me everything important about my restaurant."] },
];
