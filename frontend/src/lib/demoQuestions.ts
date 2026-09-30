// Prompted questions for the Demo Restaurant OS, in the words an owner would use.
// Each question carries the area it belongs to, so the answer never depends on a
// "focus area" picker. Every one can be answered from the demo scenario, and together they
// show what each part of the software can do: forecasts, run-out dates, order lists,
// staffing, margins, cash checks and more.
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
      {
        label: "Sales",
        note: "Money coming in, and what to expect",
        slug: "revenue",
        questions: [
          "How are my sales this week?",
          "What should I expect next week?",
          "Why is Monday so quiet?",
          "Which day will be my busiest, and why?",
          "Am I earning more than last week?",
          "How much should I expect to take on Saturday?",
          "What is an average order worth?",
          "How can I get more sales on quiet days?",
        ],
      },
      {
        label: "Orders",
        note: "What guests are ordering right now",
        slug: "orders",
        questions: [
          "Are any orders running late?",
          "How many orders are still being prepared?",
          "Which way do guests order most?",
          "What should I do about the late delivery?",
          "Why do orders get delayed?",
          "How many orders did we complete today?",
        ],
      },
      {
        label: "Kitchen",
        note: "How fast food is coming out",
        slug: "kitchen",
        questions: [
          "Where is the kitchen slowing down?",
          "What should I fix before the dinner rush?",
          "How many plates will the kitchen prepare on Saturday?",
          "Why is the grill so slow?",
          "How long does a dish take on average?",
          "Do I need extra hands in the kitchen this week?",
        ],
      },
      {
        label: "Stock",
        note: "What is on the shelf and what to order",
        slug: "stock",
        questions: [
          "What am I about to run out of?",
          "What should I order today?",
          "Will I have enough beef for the week?",
          "When will the chicken run out?",
          "Which ingredients should I use first?",
          "Which dishes are affected if beef runs out?",
          "How much food am I at risk of wasting?",
          "Why does stock run out faster at the weekend?",
        ],
      },
      {
        label: "Bookings",
        note: "Who is coming, and how busy it will be",
        slug: "bookings",
        questions: [
          "Who is booked tonight?",
          "Which bookings still need a reply?",
          "How many guests should I expect on Saturday?",
          "Should I keep tables free for walk-ins?",
          "What is my no-show rate?",
          "What should I do about the waitlist?",
        ],
      },
      {
        label: "Team",
        note: "Who is working, and what it costs",
        slug: "team",
        questions: [
          "Is my staff overtime too high?",
          "Is dinner properly staffed?",
          "How many people do I need on Saturday?",
          "How can I cut overtime without hurting service?",
          "What share of my sales goes on staff?",
          "Which day can I run with fewer people?",
        ],
      },
    ],
  },
  {
    id: "money",
    title: "Money and buying",
    areas: [
      {
        label: "Menu and prices",
        note: "What earns you the most",
        slug: "menu",
        questions: [
          "Which dish earns me the most?",
          "Should I raise the price of pilau?",
          "How can I improve my menu margins?",
          "Which dish keeps the least per plate?",
          "What happens if I raise the pilau price by KES 30?",
          "Which dish should I promote?",
          "What does each dish cost me to make?",
        ],
      },
      {
        label: "Money left",
        note: "What is left after costs",
        slug: "finance",
        questions: [
          "How much is left after all my costs?",
          "Is contribution the same as profit?",
          "Where does my money go each day?",
          "How much of every shilling goes on ingredients?",
          "What should I check before calling today profitable?",
        ],
      },
      {
        label: "Costs",
        note: "What it costs to run the place",
        slug: "expenses",
        questions: [
          "What costs me the most?",
          "How much do I spend on staff?",
          "How can I lower my costs?",
          "Why does cutting waste matter more than cutting staff?",
          "What share of my sales goes on running costs?",
        ],
      },
      {
        label: "Suppliers",
        note: "Who supplies you and how reliable they are",
        slug: "suppliers",
        questions: [
          "Is any supplier late?",
          "Who should I call today?",
          "Which supplier raised their prices?",
          "Which supplier provides my beef?",
          "Why is the late meat delivery a problem?",
          "Is it worth comparing prices for rice and oil?",
        ],
      },
      {
        label: "Buying orders",
        note: "What you have ordered and what to order",
        slug: "purchasing",
        questions: [
          "What orders are waiting for me?",
          "What should I order this week?",
          "Which order is overdue?",
          "Should I approve the dry goods order?",
          "Which supplier should I order from first?",
          "When do I need to order the produce?",
        ],
      },
      {
        label: "Cash and M-Pesa",
        note: "Does the money match the sales",
        slug: "cash-reconciliation",
        questions: [
          "Does my money match my sales?",
          "Why is KES 1,200 unmatched?",
          "What should I do about the unmatched payment?",
          "How much has been settled today?",
          "Is a difference the same as a loss?",
        ],
      },
    ],
  },
  {
    id: "growth",
    title: "Growing and staying safe",
    areas: [
      {
        label: "How guests order",
        note: "Dine-in, takeaway and delivery",
        slug: "pos",
        questions: [
          "How are guests ordering?",
          "How many takeaway orders do I get?",
          "Should I push takeaway or delivery?",
          "Where should I put my staff, based on how guests order?",
        ],
      },
      {
        label: "Marketing",
        note: "Bringing guests in and back",
        slug: "marketing",
        questions: [
          "What offer could bring guests back?",
          "How many of my guests are returning?",
          "What special could I run on a quiet day?",
          "How can I use the vegetables that are close to expiry in an offer?",
          "How would I know if an offer worked?",
        ],
      },
      {
        label: "Unusual activity",
        note: "Things worth a second look",
        slug: "risk",
        questions: [
          "Is there anything unusual I should check?",
          "Is the unmatched payment theft?",
          "Why was an order voided after it was cooked?",
          "How do I check without accusing my team?",
        ],
      },
      {
        label: "Alerts",
        note: "Everything asking for your attention",
        slug: "notifications",
        questions: [
          "What needs my attention today?",
          "What is urgent right now?",
          "What should I deal with first?",
          "Are there alerts I can leave for now?",
        ],
      },
    ],
  },
  {
    id: "setup",
    title: "Understanding your numbers",
    areas: [
      {
        label: "Ideas",
        note: "The few decisions that matter most",
        slug: "intelligence",
        questions: [
          "Where can I save money?",
          "What are the biggest chances I have this week?",
          "What should I focus on today, and why?",
          "Which idea is easiest to start today?",
          "How much could I gain each day if everything works?",
          "Have I actually earned any of these savings yet?",
        ],
      },
      {
        label: "Where the numbers come from",
        note: "How far to trust them",
        slug: "data-trust",
        questions: [
          "Where do these numbers come from?",
          "Can I trust these figures?",
          "Is any real restaurant data being used here?",
          "What would change with my own restaurant connected?",
        ],
      },
      {
        label: "Decisions made",
        note: "A record of what was suggested",
        slug: "audit",
        questions: [
          "What decisions have been made?",
          "Has anything actually been changed?",
          "What is waiting for me to decide?",
          "Why does a record of decisions matter?",
        ],
      },
      {
        label: "Setup",
        note: "How your restaurant is set up",
        slug: "settings",
        questions: [
          "How is my restaurant set up?",
          "Which currency and timezone does it use?",
          "Is my restaurant kept separate from others?",
          "Can this demo change my real records?",
        ],
      },
    ],
  },
];
