"use client";

/**
 * InsightsPanel — the "Insights" tab. All 14 existing module sections, kept
 * exactly as they are (each still fetches independently and keeps its _full/
 * sub-dashboard link), regrouped under Money / Operations / Growth / Risk so
 * the owner navigates by concern, not by internal architecture.
 */
import dynamic from "next/dynamic";
import SectionCard from "@/components/ui/SectionCard";
import { InsightCard } from "@/components/ai/InsightCard";
import { classify } from "./overview/taxonomy";
import type { HealthBreakdownItem, Risk, Opportunity, RecentAiAction } from "./overview/types";

const RevenueForecastSection = dynamic(() => import("./RevenueForecastSection"));
const ProfitSection = dynamic(() => import("./ProfitSection"));
const PricingSection = dynamic(() => import("./PricingSection"));
const CashSection = dynamic(() => import("./CashSection"));
const KdsSection = dynamic(() => import("./KdsSection"));
const MenuEngineeringSection = dynamic(() => import("./MenuEngineeringSection"));
const InventoryPredictionsSection = dynamic(() => import("./InventoryPredictionsSection"));
const SupplyChainSection = dynamic(() => import("./SupplyChainSection"));
const LaborSection = dynamic(() => import("./LaborSection"));
const StrategyAgent = dynamic(() => import("@/components/ai/StrategyAgent").then((m) => m.StrategyAgent));
const DecisionsSection = dynamic(() => import("./DecisionsSection"));
const WhatIfSimulator = dynamic(() => import("@/components/ai/WhatIfSimulator").then((m) => m.WhatIfSimulator));
const DigitalTwin = dynamic(() => import("@/components/ai/DigitalTwin").then((m) => m.DigitalTwin));
const HealthBoostSection = dynamic(() => import("./HealthBoostSection"));
const FraudSection = dynamic(() => import("./FraudSection"));
const GraphImpactSection = dynamic(() => import("./GraphImpactSection"));
const DataQualitySection = dynamic(() => import("./DataQualitySection"));

function GroupLabel({ children }: { children: string }) {
    return (
        <p className="text-[10px] font-semibold uppercase tracking-wider text-text-dim pt-2">{children}</p>
    );
}

export default function InsightsPanel({
    breakdown,
    score,
    risks,
    opportunities,
    recentAiActions,
}: {
    breakdown: HealthBreakdownItem[];
    score: number;
    risks: Risk[];
    opportunities: Opportunity[];
    recentAiActions: RecentAiAction[];
}) {
    return (
        <div className="space-y-6">
            {/* Money */}
            <div className="space-y-4">
                <GroupLabel>Money</GroupLabel>
                <RevenueForecastSection />
                <ProfitSection />
                <PricingSection />
                <CashSection />
            </div>

            {/* Operations */}
            <div className="space-y-4">
                <GroupLabel>Operations</GroupLabel>
                <KdsSection />
                <MenuEngineeringSection />
                <InventoryPredictionsSection />
                <SupplyChainSection />
                <LaborSection />
            </div>

            {/* Growth */}
            <div className="space-y-4">
                <GroupLabel>Growth</GroupLabel>
                <StrategyAgent />
                <DecisionsSection />
                <WhatIfSimulator />
                <DigitalTwin />
                <HealthBoostSection breakdown={breakdown} score={score} />

                <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                    <SectionCard title={`Active risks (${risks.length})`}>
                        {risks.length === 0 ? (
                            <p className="text-sm text-success">No active risks — everything looks stable.</p>
                        ) : (
                            <div className="space-y-2">
                                {risks.slice(0, 5).map((r, i) => (
                                    <InsightCard
                                        key={i}
                                        what={r.risk}
                                        why={r.detail}
                                        cls={classify(r.severity, "risk")}
                                        explainItem={r}
                                        explainLabel={r.risk}
                                    />
                                ))}
                            </div>
                        )}
                    </SectionCard>

                    <SectionCard title="Opportunities">
                        {opportunities.length === 0 ? (
                            <p className="text-sm text-text-dim">No opportunities flagged yet — keep adding data.</p>
                        ) : (
                            <div className="space-y-2">
                                {opportunities.map((o, i) => (
                                    <InsightCard
                                        key={i}
                                        what={o.opportunity}
                                        why={o.detail}
                                        impact={o.potential ? `Potential: ${o.potential}` : undefined}
                                        cls="opportunity"
                                        explainItem={o}
                                        explainLabel={o.opportunity}
                                    />
                                ))}
                            </div>
                        )}
                    </SectionCard>
                </div>
            </div>

            {/* Risk & trust */}
            <div className="space-y-4">
                <GroupLabel>Risk</GroupLabel>
                <FraudSection />
                <GraphImpactSection />
                <DataQualitySection />

                <SectionCard title="Recent AI actions">
                    {recentAiActions.length === 0 ? (
                        <p className="text-sm text-text-dim">No AI actions logged yet.</p>
                    ) : (
                        <div className="space-y-2">
                            {recentAiActions.map((log, i) => (
                                <div key={i} className="flex justify-between items-center py-2 border-b border-surface-hover last:border-0">
                                    <div>
                                        <p className="text-sm text-text">{log.action}</p>
                                        <p className="text-xs text-text-dim">{log.agent}</p>
                                    </div>
                                    <span className="text-xs text-text-dim bg-surface px-2 py-1 rounded-md whitespace-nowrap">{log.time}</span>
                                </div>
                            ))}
                        </div>
                    )}
                </SectionCard>
            </div>
        </div>
    );
}
