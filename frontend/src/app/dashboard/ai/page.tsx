"use client";

/**
 * /dashboard/ai — "{Restaurant} Overview"
 *
 * Formerly the "AI Command Center". Reframed per the product critique: the
 * owner should see one coherent business system that answers "what happened,
 * what's happening, what's wrong, what should I do" — not a bag of AI modules.
 *
 *   - Today tab: Needs-attention hero, Today stats, Business health, Performance.
 *   - Insights tab: every module grouped by concern (Money / Operations / Growth / Risk).
 *
 * Still true from the previous version:
 *   - Lives inside the main dashboard layout (same sidebar/nav as POS, Kitchen etc)
 *   - Uses the shared api.ts axios client (automatic auth, 401 redirect, base URL)
 *   - Shows REAL data from the backend AI agents
 *   - Falls back to a helpful empty state (not fake data) for new restaurants
 */

import { useEffect, useState } from "react";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Brain, TrendingUp, AlertTriangle, Shield, Activity, ArrowRight } from "lucide-react";
import Link from "next/link";
import EmptyState from "@/components/ui/EmptyState";
import AiTabs, { tabFromHash, type AiTabId } from "./_components/AiTabs";
import OverviewHeader from "./_components/overview/OverviewHeader";
import AttentionHero from "./_components/overview/AttentionHero";
import TodayStats from "./_components/overview/TodayStats";
import BusinessHealth from "./_components/overview/BusinessHealth";
import PerformanceSection from "./_components/overview/PerformanceSection";
import InsightsPanel from "./_components/InsightsPanel";
import { rankAttention } from "./_components/overview/taxonomy";
import { getErrorMessage } from "@/lib/errors";
import type { DashboardData } from "./_components/overview/types";

export default function AiDashboard() {
    const { user } = useAuth();
    const [data, setData] = useState<DashboardData | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");
    const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
    // Active view, synced to the URL hash so refresh/back keeps it. "today" is
    // the default landing view. Read in an effect (not the useState initializer)
    // to avoid an SSR/client hydration mismatch on #insights URLs.
    const [activeTab, setActiveTab] = useState<AiTabId>("today");

    const restaurantName = user?.restaurant_name || "Your Restaurant";

    const fetchData = async () => {
        setLoading(true);
        setError("");
        try {
            const res = await api.get("/ai/dashboard");
            setData(res.data);
            setLastUpdated(new Date());
        } catch (e) {
            setError(getErrorMessage(e, "Could not load your overview"));
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => { fetchData(); }, []);

    // Restore the view from a #hash URL after hydration, then keep back/forward
    // working via hashchange.
    useEffect(() => {
        setActiveTab(tabFromHash(window.location.hash));
        const onHashChange = () => setActiveTab(tabFromHash(window.location.hash));
        window.addEventListener("hashchange", onHashChange);
        return () => window.removeEventListener("hashchange", onHashChange);
    }, []);

    const selectTab = (id: AiTabId) => {
        setActiveTab(id);
        if (id === "today") {
            history.replaceState(null, "", window.location.pathname);
        } else {
            history.replaceState(null, "", `#${id}`);
        }
    };

    if (loading) {
        return (
            <div className="space-y-4">
                <div className="bg-surface rounded-xl h-8 w-48 animate-pulse" />
                <div className="bg-surface rounded-xl h-40 animate-pulse" />
                <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
                    {[...Array(4)].map((_, i) => (
                        <div key={i} className="bg-surface rounded-xl h-20 animate-pulse" />
                    ))}
                </div>
            </div>
        );
    }

    // No data or genuinely empty restaurant → helpful onboarding empty state.
    // Keyed on real setup/activity signals (menu items + 30d revenue), not on
    // today's order count, so a quiet day doesn't mask a live restaurant.
    const isNewRestaurant = !data || (!data.quick_stats.menu_items && !data.quick_stats.total_revenue_30d);
    if (isNewRestaurant && !error) {
        return (
            <div className="space-y-6">
                <EmptyState
                    pageTitle={`${restaurantName} Overview`}
                    pageSubtitle="Getting started"
                    icon={Brain}
                    title="Your AI agents are ready"
                    description="Add menu items, record some orders, and your AI agents will start generating real insights — pricing recommendations, inventory alerts, revenue forecasts."
                    actions={
                        <>
                            <Link
                                href="/dashboard/menu"
                                className="flex items-center gap-2 px-4 py-2 rounded-lg bg-[var(--accent)] text-bg font-semibold text-sm hover:bg-[var(--accent-hover)] transition-colors"
                            >
                                Add menu items <ArrowRight className="w-3.5 h-3.5" />
                            </Link>
                            <Link
                                href="/dashboard/pos"
                                className="flex items-center gap-2 px-4 py-2 rounded-lg bg-surface border border-border text-text text-sm hover:bg-surface-hover transition-colors"
                            >
                                Record first order
                            </Link>
                        </>
                    }
                />
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    {[
                        { icon: TrendingUp, label: "Pricing Intelligence", desc: "Surge pricing, margin alerts, delivery gap analysis" },
                        { icon: Shield, label: "Stock Monitoring", desc: "Predictive restock alerts before you run out" },
                        { icon: Activity, label: "Revenue Forecasting", desc: "7-day and 30-day predictions with confidence bands" },
                    ].map((agent) => (
                        <div key={agent.label} className="rounded-xl border border-surface-hover bg-[#0f0f0f] p-5">
                            <agent.icon className="w-5 h-5 text-[var(--accent)] mb-3" />
                            <p className="text-text font-medium text-sm">{agent.label}</p>
                            <p className="text-text-dim text-xs mt-1">{agent.desc}</p>
                        </div>
                    ))}
                </div>
            </div>
        );
    }

    if (error) {
        return (
            <div className="flex flex-col items-center justify-center min-h-[50vh] space-y-4">
                <AlertTriangle className="w-10 h-10 text-amber-400" />
                <p className="text-text font-medium">Could not load your overview</p>
                <p className="text-text-dim text-sm text-center max-w-sm">{error}</p>
                <button
                    onClick={fetchData}
                    className="px-4 py-2 bg-[var(--accent)] text-bg font-semibold rounded-lg text-sm hover:bg-[var(--accent-hover)]"
                >
                    Retry
                </button>
            </div>
        );
    }

    const d = data!;
    const attention = rankAttention(d.risks, d.alerts, d.opportunities);

    const panelProps = (id: AiTabId) => ({
        id: `ai-panel-${id}`,
        role: "tabpanel" as const,
        "aria-labelledby": `ai-tab-${id}`,
    });

    return (
        <div className="space-y-6">
            <OverviewHeader restaurantName={restaurantName} lastUpdated={lastUpdated} onRefresh={fetchData} />

            <AiTabs active={activeTab} onChange={selectTab} />

            {activeTab === "today" && (
                <div {...panelProps("today")} className="space-y-6">
                    <AttentionHero items={attention} onViewAll={() => selectTab("insights")} />
                    <TodayStats qs={d.quick_stats} />
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 items-start">
                        <BusinessHealth
                            score={d.health_score}
                            breakdown={d.health_breakdown}
                            onImprove={() => selectTab("insights")}
                        />
                        <PerformanceSection />
                    </div>
                </div>
            )}

            {activeTab === "insights" && (
                <div {...panelProps("insights")}>
                    <InsightsPanel
                        breakdown={d.health_breakdown}
                        score={d.health_score}
                        risks={d.risks}
                        opportunities={d.opportunities}
                        recentAiActions={d.recent_ai_actions}
                    />
                </div>
            )}
        </div>
    );
}
