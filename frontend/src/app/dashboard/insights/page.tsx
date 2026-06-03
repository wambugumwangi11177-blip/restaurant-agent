"use client";

import { useState, useEffect } from "react";

const demoData = {
  restaurant: "Lavy",
  owner: "James",
  health_score: 84,
  pricing: {
    revenue_opportunity: 87400,
    surge_opportunities: 4,
    underpriced_items: 3,
    recommendations: [
      { item: "Sticky Wings", current: 1190, suggested: 1390, when: "Fri & Sat evenings", impact: 31200, type: "SURGE" },
      { item: "Goat Mandi", current: 2100, suggested: 2400, when: "Weekend lunch & dinner", impact: 28400, type: "SURGE" },
      { item: "Caffe Latte", current: 320, suggested: 380, when: "All times", impact: 14200, type: "REPRICE" },
      { item: "Highwayman Burger", current: 1190, suggested: 1350, when: "Friday evenings", impact: 13600, type: "SURGE" },
    ],
    top3: [
      "Increase Sticky Wings price by KES 200 on weekends — customers won't notice, you gain KES 31,200/month",
      "Goat Mandi is underpriced vs competitors — KES 300 increase still below market rate",
      "Your coffee prices are below Nairobi benchmark — safe to reprice all coffee items up 15-20%",
    ],
  },
  profit: {
    total_profit_30d: 1847200,
    margin: 61.4,
    food_cost: 34.1,
    food_cost_status: "HEALTHY",
    leaks_total: 38400,
    stars: ["Sticky Wings", "Passion Mojito", "Goat Mandi", "Highwayman Burger"],
    plowhorses: ["Chicken Biryani", "Fish & Chips", "Large Platter"],
    puzzles: ["Prawns Tagliatelle", "Pan-Seared Salmon", "T-Bone Steak"],
    dogs: ["Greek Salad", "Oats Porridge", "Linguine Pomodoro"],
    leaks: [
      { title: "Fish & Chips Undermargin", desc: "Food cost at 52% — above healthy 35% threshold", amount: 24800, severity: "HIGH", action: "Increase price from KES 1,490 → KES 1,690" },
      { title: "Large Platter Inconsistency", desc: "Portion sizes vary 18% — cost fluctuates weekly", amount: 13600, severity: "MEDIUM", action: "Standardize portioning with kitchen weight guide" },
    ],
    upsells: [
      { a: "Highwayman Burger", b: "Chips", rate: "68%", uplift: 18400 },
      { a: "Goat Mandi", b: "Somali Tea", rate: "54%", uplift: 14200 },
    ],
  },
  whatsapp: {
    morning: `🌅 Good morning James!\n\n📊 *Yesterday at Lavy*\nRevenue: KES 52,400\nOrders: 47 (+12% vs last Thu)\n\n🏆 Top Sellers:\n1. Passion Mojito — 23 orders\n2. Sticky Wings — 18 orders\n3. Goat Mandi — 11 orders\n\n💰 Payments:\nM-Pesa: 61% | Cash: 24% | Card: 15%\n\n⚠️ Alert: Chicken stock low — reorder by 3pm\n\n🎯 Today's Focus:\nFriday evening incoming — your busiest window. Prep extra Goat Mandi and Passion Mojitos before 6pm.\n\nPowered by Leviii AI 🤖`,
    time: "Today, 8:00 AM",
    stock_alerts: [
      { item: "Chicken", qty: "3kg", hours: 4, level: "URGENT" },
      { item: "Passion Fruit", qty: "2kg", hours: 11, level: "WARNING" },
    ],
    winback: [
      { name: "Aisha Mohamed", days: 24, fav: "Prawns Tagliatelle", spend: 8400 },
      { name: "Brian Mwangi", days: 28, fav: "Highwayman Burger", spend: 6200 },
      { name: "Grace Wambui", days: 22, fav: "Lotus Biscoff Shake", spend: 4800 },
    ],
  },
};

const fmt = (n: number) => `KES ${Number(n).toLocaleString()}`;

const Tag = ({ children, color }: { children: React.ReactNode; color: string }) => {
  const colors: Record<string, string> = {
    green: "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30",
    red: "bg-red-500/20 text-red-400 border border-red-500/30",
    amber: "bg-amber-500/20 text-amber-400 border border-amber-500/30",
    blue: "bg-blue-500/20 text-blue-400 border border-blue-500/30",
    purple: "bg-purple-500/20 text-purple-400 border border-purple-500/30",
  };
  return <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${colors[color]}`}>{children}</span>;
};

const Section = ({ title, subtitle, icon, children }: { title: string; subtitle?: string; icon: string; children: React.ReactNode }) => (
  <div className="mb-8">
    <div className="flex items-center gap-3 mb-4">
      <div className="w-10 h-10 rounded-xl bg-amber-500/20 flex items-center justify-center text-xl">{icon}</div>
      <div>
        <h2 className="text-white font-bold text-lg leading-tight">{title}</h2>
        {subtitle && <p className="text-zinc-400 text-sm">{subtitle}</p>}
      </div>
    </div>
    {children}
  </div>
);

const Card = ({ children, className = "" }: { children: React.ReactNode; className?: string }) => (
  <div className={`bg-zinc-900 border border-zinc-800 rounded-2xl p-4 ${className}`}>{children}</div>
);

export default function InsightsPage() {
  const [tab, setTab] = useState("pricing");
  const [msgVisible, setMsgVisible] = useState(false);
  const d = demoData;

  useEffect(() => {
    const t = setTimeout(() => setMsgVisible(true), 400);
    return () => clearTimeout(t);
  }, []);

  const tabs = [
    { id: "pricing", label: "💰 Pricing" },
    { id: "profit", label: "📊 Profit" },
    { id: "whatsapp", label: "💬 WhatsApp Brain" },
  ];

  return (
    <div className="text-white">
      {/* Page header */}
      <div className="pb-4 border-b border-zinc-800 mb-4">
        <div className="flex items-center justify-between mb-1">
          <div>
            <h1 className="text-2xl font-black text-white tracking-tight">AI Insights</h1>
            <p className="text-zinc-400 text-sm">Lavy Restaurant — Live Intelligence</p>
          </div>
          <div className="text-right">
            <div className="text-3xl font-black text-amber-400">{d.health_score}</div>
            <div className="text-xs text-zinc-500">Health Score</div>
          </div>
        </div>

        {/* Demo banner */}
        <div className="mt-3 bg-amber-500/10 border border-amber-500/20 rounded-xl px-3 py-2 flex items-center gap-2">
          <span className="text-amber-400 text-sm">📊</span>
          <span className="text-amber-300 text-xs font-medium">Demo Mode — Showing sample data for Lavy restaurant</span>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-2 pb-4 overflow-x-auto">
        {tabs.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`flex-shrink-0 px-4 py-2 rounded-xl text-sm font-semibold transition-all ${
              tab === t.id ? "bg-amber-500 text-black" : "bg-zinc-800 text-zinc-400 hover:text-white"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="pb-10">
        {/* ── PRICING INTELLIGENCE ── */}
        {tab === "pricing" && (
          <div>
            <Section icon="💰" title="Pricing Intelligence" subtitle="Demand-based pricing & competitor benchmarks">
              {/* Opportunity summary */}
              <div className="grid grid-cols-3 gap-3 mb-4">
                {[
                  { label: "Revenue Opportunity", value: fmt(d.pricing.revenue_opportunity), color: "text-emerald-400" },
                  { label: "Surge Windows", value: d.pricing.surge_opportunities, color: "text-amber-400" },
                  { label: "Underpriced Items", value: d.pricing.underpriced_items, color: "text-red-400" },
                ].map((s, i) => (
                  <Card key={i} className="text-center">
                    <div className={`text-xl font-black ${s.color}`}>{s.value}</div>
                    <div className="text-zinc-500 text-xs mt-1 leading-tight">{s.label}</div>
                  </Card>
                ))}
              </div>

              {/* Recommendations */}
              <div className="space-y-3 mb-4">
                {d.pricing.recommendations.map((r, i) => (
                  <Card key={i}>
                    <div className="flex items-start justify-between gap-2 mb-2">
                      <div>
                        <span className="font-bold text-white">{r.item}</span>
                        <div className="text-zinc-400 text-xs mt-0.5">{r.when}</div>
                      </div>
                      <Tag color={r.type === "SURGE" ? "amber" : "blue"}>{r.type}</Tag>
                    </div>
                    <div className="flex items-center gap-3 mb-2">
                      <div className="text-zinc-500 line-through text-sm">{fmt(r.current)}</div>
                      <div className="text-amber-400">→</div>
                      <div className="text-emerald-400 font-bold">{fmt(r.suggested)}</div>
                    </div>
                    <div className="bg-emerald-500/10 border border-emerald-500/20 rounded-lg px-3 py-1.5">
                      <span className="text-emerald-400 text-xs font-semibold">+{fmt(r.impact)}/month if implemented</span>
                    </div>
                  </Card>
                ))}
              </div>

              {/* Top 3 actions */}
              <Card>
                <div className="text-xs font-bold text-zinc-400 uppercase tracking-wider mb-3">🎯 Top 3 Actions This Week</div>
                <div className="space-y-3">
                  {d.pricing.top3.map((a, i) => (
                    <div key={i} className="flex gap-3">
                      <div className="w-6 h-6 rounded-full bg-amber-500/20 text-amber-400 text-xs flex items-center justify-center font-bold flex-shrink-0">
                        {i + 1}
                      </div>
                      <p className="text-zinc-300 text-sm leading-relaxed">{a}</p>
                    </div>
                  ))}
                </div>
              </Card>
            </Section>
          </div>
        )}

        {/* ── PROFIT INTELLIGENCE ── */}
        {tab === "profit" && (
          <div>
            <Section icon="📊" title="Profit Intelligence" subtitle="Menu profitability matrix & leak detection">
              {/* Summary */}
              <div className="grid grid-cols-2 gap-3 mb-4">
                {[
                  { label: "Est. Profit (30d)", value: fmt(d.profit.total_profit_30d), color: "text-emerald-400" },
                  { label: "Avg Margin", value: `${d.profit.margin}%`, color: "text-amber-400" },
                  { label: "Food Cost", value: `${d.profit.food_cost}%`, color: "text-emerald-400" },
                  { label: "Profit Leaks", value: fmt(d.profit.leaks_total), color: "text-red-400" },
                ].map((s, i) => (
                  <Card key={i} className="text-center">
                    <div className={`text-xl font-black ${s.color}`}>{s.value}</div>
                    <div className="text-zinc-500 text-xs mt-1">{s.label}</div>
                  </Card>
                ))}
              </div>

              {/* Food cost status */}
              <Card className="mb-4">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="text-sm font-bold text-white">Food Cost Status</div>
                    <div className="text-zinc-400 text-xs mt-0.5">Industry benchmark: 28-35%</div>
                  </div>
                  <Tag color="green">✓ HEALTHY</Tag>
                </div>
                <div className="mt-3 bg-zinc-800 rounded-full h-2">
                  <div className="bg-emerald-500 h-2 rounded-full" style={{ width: "34.1%" }}></div>
                </div>
                <div className="flex justify-between text-xs text-zinc-500 mt-1">
                  <span>0%</span>
                  <span className="text-emerald-400">34.1%</span>
                  <span>50%</span>
                </div>
              </Card>

              {/* BCG Matrix */}
              <Card className="mb-4">
                <div className="text-xs font-bold text-zinc-400 uppercase tracking-wider mb-3">Menu Performance Matrix</div>
                <div className="grid grid-cols-2 gap-3">
                  {[
                    { label: "⭐ Stars", items: d.profit.stars, color: "border-amber-500/40 bg-amber-500/5" },
                    { label: "🐄 Plowhorses", items: d.profit.plowhorses, color: "border-blue-500/40 bg-blue-500/5" },
                    { label: "❓ Puzzles", items: d.profit.puzzles, color: "border-purple-500/40 bg-purple-500/5" },
                    { label: "🐕 Dogs", items: d.profit.dogs, color: "border-red-500/40 bg-red-500/5" },
                  ].map((cat, i) => (
                    <div key={i} className={`border rounded-xl p-3 ${cat.color}`}>
                      <div className="text-xs font-bold text-white mb-2">{cat.label}</div>
                      <div className="space-y-1">
                        {cat.items.map((item, j) => (
                          <div key={j} className="text-zinc-300 text-xs">• {item}</div>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </Card>

              {/* Profit leaks */}
              <div className="space-y-3 mb-4">
                {d.profit.leaks.map((l, i) => (
                  <Card key={i} className="border-red-500/20">
                    <div className="flex items-start justify-between mb-2">
                      <div className="font-bold text-white text-sm">{l.title}</div>
                      <Tag color={l.severity === "HIGH" ? "red" : "amber"}>{l.severity}</Tag>
                    </div>
                    <p className="text-zinc-400 text-xs mb-2">{l.desc}</p>
                    <div className="bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-1.5 mb-2">
                      <span className="text-red-400 text-xs font-semibold">Losing {fmt(l.amount)}/month</span>
                    </div>
                    <div className="flex items-start gap-2">
                      <span className="text-amber-400 text-xs">→</span>
                      <span className="text-zinc-300 text-xs">{l.action}</span>
                    </div>
                  </Card>
                ))}
              </div>

              {/* Upsell */}
              <Card>
                <div className="text-xs font-bold text-zinc-400 uppercase tracking-wider mb-3">🔗 Bundle Opportunities</div>
                {d.profit.upsells.map((u, i) => (
                  <div key={i} className="flex items-center justify-between py-2 border-b border-zinc-800 last:border-0">
                    <div>
                      <div className="text-white text-sm font-medium">{u.a} + {u.b}</div>
                      <div className="text-zinc-500 text-xs">Ordered together {u.rate} of the time</div>
                    </div>
                    <div className="text-emerald-400 text-sm font-bold">+{fmt(u.uplift)}</div>
                  </div>
                ))}
              </Card>
            </Section>
          </div>
        )}

        {/* ── WHATSAPP BRAIN ── */}
        {tab === "whatsapp" && (
          <div>
            <Section icon="💬" title="WhatsApp Brain" subtitle="Daily briefings, alerts & customer retention">
              {/* Morning briefing */}
              <div className="mb-4">
                <div className="text-xs font-bold text-zinc-400 uppercase tracking-wider mb-3">🌅 Morning Briefing</div>
                <div className={`transition-all duration-700 ${msgVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-4"}`}>
                  <div className="flex justify-end mb-1">
                    <div className="text-zinc-500 text-xs">{d.whatsapp.time}</div>
                  </div>
                  <div className="flex justify-end">
                    <div className="bg-emerald-600 rounded-2xl rounded-tr-sm px-4 py-3 max-w-xs shadow-lg shadow-emerald-900/30">
                      <pre className="text-white text-xs leading-relaxed whitespace-pre-wrap font-sans">{d.whatsapp.morning}</pre>
                      <div className="flex justify-end mt-1">
                        <span className="text-emerald-200 text-xs">✓✓</span>
                      </div>
                    </div>
                  </div>
                  <div className="flex justify-end mt-1">
                    <div className="text-zinc-600 text-xs">Delivered to owner&apos;s WhatsApp</div>
                  </div>
                </div>
              </div>

              {/* Stock alerts */}
              <div className="mb-4">
                <div className="text-xs font-bold text-zinc-400 uppercase tracking-wider mb-3">⚠️ Live Stock Alerts</div>
                <div className="space-y-2">
                  {d.whatsapp.stock_alerts.map((a, i) => (
                    <Card key={i} className={a.level === "URGENT" ? "border-red-500/40" : "border-amber-500/40"}>
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-3">
                          <div className={`w-2 h-2 rounded-full ${a.level === "URGENT" ? "bg-red-400 animate-pulse" : "bg-amber-400"}`}></div>
                          <div>
                            <div className="text-white font-semibold text-sm">{a.item}</div>
                            <div className="text-zinc-400 text-xs">{a.qty} remaining</div>
                          </div>
                        </div>
                        <div className="text-right">
                          <Tag color={a.level === "URGENT" ? "red" : "amber"}>{a.level}</Tag>
                          <div className="text-zinc-500 text-xs mt-1">~{a.hours}hrs left</div>
                        </div>
                      </div>
                    </Card>
                  ))}
                </div>
              </div>

              {/* Smart receipt preview */}
              <div className="mb-4">
                <div className="text-xs font-bold text-zinc-400 uppercase tracking-wider mb-3">🧾 Smart Receipt Preview</div>
                <div className="flex justify-start">
                  <div className="bg-zinc-800 border border-zinc-700 rounded-2xl rounded-tl-sm px-4 py-3 max-w-xs">
                    <pre className="text-zinc-200 text-xs leading-relaxed whitespace-pre-wrap font-sans">{`🍽️ Thank you for dining at Lavy!

Hi Aisha 👋

Your order:
• 1x Prawns Tagliatelle — KES 1,490
• 1x Passion Mojito — KES 480

*Total: KES 1,970*
Paid via: M-Pesa ✓

We hope you enjoyed your meal!
See you again soon 😊

Lavy — Powered by Leviii AI`}</pre>
                    <div className="text-zinc-500 text-xs mt-1">Sent with customer consent</div>
                  </div>
                </div>
              </div>

              {/* Winback */}
              <div>
                <div className="text-xs font-bold text-zinc-400 uppercase tracking-wider mb-3">
                  💌 Customer Winback — {d.whatsapp.winback.length} ready
                </div>
                <div className="space-y-3">
                  {d.whatsapp.winback.map((w, i) => (
                    <Card key={i}>
                      <div className="flex items-start justify-between mb-2">
                        <div>
                          <div className="text-white font-semibold text-sm">{w.name}</div>
                          <div className="text-zinc-400 text-xs">Away {w.days} days • Loves {w.fav}</div>
                        </div>
                        <div className="text-right">
                          <div className="text-emerald-400 text-sm font-bold">{fmt(w.spend)}</div>
                          <div className="text-zinc-500 text-xs">lifetime</div>
                        </div>
                      </div>
                      <div className="bg-zinc-800 rounded-xl p-3">
                        <p className="text-zinc-300 text-xs leading-relaxed">
                          Hey {w.name.split(" ")[0]} 👋 We miss you at Lavy! It&apos;s been {w.days} days since your last visit. Your favourite{" "}
                          <strong>{w.fav}</strong> is waiting for you 😊 Come back this week for something special!
                        </p>
                      </div>
                    </Card>
                  ))}
                </div>
              </div>
            </Section>
          </div>
        )}
      </div>
    </div>
  );
}
