"use client";

import { TrendingUp, TrendingDown } from "lucide-react";
import type { MenuInsightsSummary, MenuRecommendation } from "./types";

function friendlyRec(text: string) {
    return text
        .replace(/Star/g, "top seller")
        .replace(/Plowhorse/g, "popular item")
        .replace(/Puzzle/g, "hidden gem")
        .replace(/Dog/g, "slow mover");
}

interface MenuInsightsPanelProps {
    summary: MenuInsightsSummary;
    recommendations: MenuRecommendation[];
}

/**
 * "What we found about your menu" card — pure display of the AI menu
 * engineering summary/recommendations, extracted from MenuEditor unmodified.
 */
export default function MenuInsightsPanel({ summary, recommendations }: MenuInsightsPanelProps) {
    if (!(summary.stars > 0 || summary.dogs > 0 || recommendations.length > 0)) return null;

    return (
        <div className="bg-surface border border-border rounded-xl">
            <div className="px-4 py-3 border-b border-surface-hover">
                <p className="text-xs font-semibold text-text">What we found about your menu</p>
            </div>
            {/* Performance summary */}
            <div className="px-4 py-3 flex flex-wrap gap-2">
                {summary.stars > 0 && (
                    <span className="text-[10px] px-2 py-1 rounded-full bg-success/10 text-success flex items-center gap-1">
                        <TrendingUp className="w-3 h-3" /> {summary.stars} top seller{summary.stars > 1 ? "s" : ""}
                    </span>
                )}
                {summary.puzzles > 0 && (
                    <span className="text-[10px] px-2 py-1 rounded-full bg-info/10 text-info">
                        {summary.puzzles} hidden gem{summary.puzzles > 1 ? "s" : ""} — profitable but not selling enough
                    </span>
                )}
                {summary.plowhorses > 0 && (
                    <span className="text-[10px] px-2 py-1 rounded-full bg-warning/10 text-warning">
                        {summary.plowhorses} popular but thin margin
                    </span>
                )}
                {summary.dogs > 0 && (
                    <span className="text-[10px] px-2 py-1 rounded-full bg-danger/10 text-danger flex items-center gap-1">
                        <TrendingDown className="w-3 h-3" /> {summary.dogs} slow mover{summary.dogs > 1 ? "s" : ""} — think about removing
                    </span>
                )}
                {summary.avg_food_cost_pct > 0 && (
                    <span className="text-[10px] px-2 py-1 rounded-full bg-text-muted/10 text-text-muted">
                        Food costs around {summary.avg_food_cost_pct.toFixed(0)}% of your prices
                    </span>
                )}
            </div>
            {/* Suggestions */}
            {recommendations.length > 0 && (
                <div className="px-4 pb-3 space-y-2">
                    <p className="text-[10px] text-text-dim uppercase tracking-wider">Suggestions</p>
                    {recommendations.slice(0, 3).map((rec, i: number) => (
                        <div key={i} className="flex items-start gap-2 text-xs">
                            <span className="text-accent mt-0.5">💡</span>
                            <div>
                                <p className="text-text">{friendlyRec(rec.reason || rec.message || "")}</p>
                                {rec.action && <p className="text-text-dim mt-0.5">{rec.action}</p>}
                                {rec.estimated_impact && (
                                    <p className="text-[10px] text-success mt-0.5">Could mean {rec.estimated_impact}</p>
                                )}
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}
