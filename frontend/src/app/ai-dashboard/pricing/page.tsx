"use client";

import React, { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { DollarSign, TrendingUp, TrendingDown, RefreshCw, AlertTriangle, CheckCircle } from 'lucide-react';
import { MetricCard } from '@/components/ai/MetricCard';
import { useAuth } from '@/context/AuthContext';

interface PricingRec {
  item_id: number;
  item_name: string;
  category: string;
  type: 'SURGE' | 'REPRICE' | 'STIMULATE';
  current_price: number;
  suggested_price: number;
  price_change_pct: number;
  reason: string;
  when: string;
  monthly_impact_cents: number;
  recommendation_strength: number;
  margin_pct: number;
  new_margin_pct: number;
}

interface PricingData {
  summary: {
    total_recommendations: number;
    total_revenue_opportunity_cents: number;
    surge_opportunities: number;
    reprice_needed: number;
    stimulate_candidates: number;
    items_below_margin_floor: number;
    items_analysed: number;
  };
  recommendations: PricingRec[];
  delivery_gaps: unknown[];
}

const typeStyles: Record<string, string> = {
  SURGE: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30',
  REPRICE: 'bg-red-500/20 text-red-400 border-red-500/30',
  STIMULATE: 'bg-amber-500/20 text-amber-400 border-amber-500/30',
};

export default function PricingIntelligence() {
  const { token } = useAuth();
  const [data, setData] = useState<PricingData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [actionLoading, setActionLoading] = useState<number | null>(null);
  const [actionFeedback, setActionFeedback] = useState<Record<number, string>>({});

  const fetchData = async () => {
    if (!token) return;
    setLoading(true);
    setError('');
    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/ai/pricing`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error(`API error: ${res.status}`);
      setData(await res.json());
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchData(); }, [token]);

  const handleApprove = async (recId: number) => {
    setActionLoading(recId);
    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/ai/pricing/${recId}/approve`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      });
      const result = await res.json();
      setActionFeedback(prev => ({ ...prev, [recId]: result.message || 'Approved!' }));
      setTimeout(() => fetchData(), 1500);
    } catch {
      setActionFeedback(prev => ({ ...prev, [recId]: 'Action failed — try again' }));
    } finally {
      setActionLoading(null);
    }
  };

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] space-y-4">
        <div className="w-16 h-16 border-4 border-indigo-500/30 border-t-indigo-400 rounded-full animate-spin" />
        <p className="text-slate-400 text-sm animate-pulse">Analysing pricing intelligence…</p>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] space-y-4">
        <AlertTriangle className="w-12 h-12 text-amber-400" />
        <p className="text-slate-300 font-medium">Could not load pricing data</p>
        <p className="text-slate-500 text-sm">{error}</p>
        <button onClick={fetchData} className="px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm hover:bg-indigo-700">Retry</button>
      </div>
    );
  }

  const s = data.summary;
  const opp = `KES ${(s.total_revenue_opportunity_cents / 100).toLocaleString()}`;

  return (
    <div className="space-y-8">
      <motion.div initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }} className="flex items-start justify-between">
        <div>
          <h1 className="text-3xl font-bold text-white">Pricing Intelligence</h1>
          <p className="text-slate-400 mt-1">AI-powered pricing based on real demand patterns — {s.items_analysed} items analysed</p>
        </div>
        <button onClick={fetchData} className="flex items-center space-x-2 px-3 py-2 rounded-lg bg-white/5 border border-white/10 text-slate-400 hover:text-white transition-all text-sm">
          <RefreshCw className="w-4 h-4" />
          <span>Refresh</span>
        </button>
      </motion.div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <MetricCard title="Surge Opportunities" value={String(s.surge_opportunities)} trend="up" icon={<TrendingUp className="w-5 h-5" />} delay={0.1} />
        <MetricCard title="Need Repricing" value={String(s.reprice_needed)} trend="down" icon={<TrendingDown className="w-5 h-5" />} delay={0.15} />
        <MetricCard title="Stimulate Demand" value={String(s.stimulate_candidates)} icon={<DollarSign className="w-5 h-5" />} delay={0.2} />
        <MetricCard title="Monthly Opportunity" value={opp} trend="up" icon={<DollarSign className="w-5 h-5" />} delay={0.25} />
      </div>

      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }}
        className="rounded-2xl border border-white/10 bg-white/5 backdrop-blur-md p-6">
        <h2 className="text-xl font-semibold text-white mb-5">
          Price Recommendations
          <span className="ml-2 text-sm font-normal text-slate-400">({s.total_recommendations} actionable)</span>
        </h2>

        {data.recommendations.length === 0 ? (
          <div className="flex items-center space-x-3 py-6 text-emerald-400">
            <CheckCircle className="w-6 h-6" />
            <div>
              <p className="font-medium">All prices optimised</p>
              <p className="text-sm text-slate-400">No changes recommended at this time. Check back after more sales data.</p>
            </div>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead>
                <tr className="border-b border-white/10">
                  {['Item', 'Current', 'Suggested', 'Type', 'Reason', 'Monthly Impact', 'Strength', 'Action'].map(h => (
                    <th key={h} className="pb-3 text-slate-400 text-xs font-medium uppercase tracking-wider pr-4">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {data.recommendations.map((rec, i) => (
                  <motion.tr key={rec.item_id} initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.4 + i * 0.05 }}
                    className="hover:bg-white/5 transition-colors">
                    <td className="py-4 pr-4">
                      <p className="text-white font-medium">{rec.item_name}</p>
                      <p className="text-xs text-slate-500">{rec.category}</p>
                    </td>
                    <td className="py-4 pr-4 text-slate-300">KES {(rec.current_price / 100).toLocaleString()}</td>
                    <td className="py-4 pr-4">
                      <span className={`font-bold ${rec.type === 'STIMULATE' ? 'text-amber-400' : 'text-emerald-400'}`}>
                        KES {(rec.suggested_price / 100).toLocaleString()}
                      </span>
                      <span className={`ml-1 text-xs ${rec.price_change_pct >= 0 ? 'text-emerald-500' : 'text-amber-500'}`}>
                        ({rec.price_change_pct >= 0 ? '+' : ''}{rec.price_change_pct}%)
                      </span>
                    </td>
                    <td className="py-4 pr-4">
                      <span className={`px-2 py-1 rounded-full text-xs font-bold border ${typeStyles[rec.type] || ''}`}>{rec.type}</span>
                    </td>
                    <td className="py-4 pr-4 text-slate-400 text-sm max-w-[200px]">
                      <p className="truncate" title={rec.reason}>{rec.reason}</p>
                    </td>
                    <td className="py-4 pr-4">
                      <span className="text-emerald-400 font-medium text-sm">
                        +KES {(rec.monthly_impact_cents / 100).toLocaleString()}/mo
                      </span>
                    </td>
                    <td className="py-4 pr-4">
                      <div className="flex items-center space-x-2">
                        <div className="w-16 bg-white/10 rounded-full h-1.5">
                          <div className="h-1.5 rounded-full bg-indigo-400" style={{ width: `${rec.recommendation_strength}%` }} />
                        </div>
                        <span className="text-slate-400 text-xs">{rec.recommendation_strength}%</span>
                      </div>
                    </td>
                    <td className="py-4">
                      {actionFeedback[rec.item_id] ? (
                        <span className="text-emerald-400 text-xs">{actionFeedback[rec.item_id]}</span>
                      ) : (
                        <button
                          onClick={() => handleApprove(rec.item_id)}
                          disabled={actionLoading === rec.item_id}
                          className="px-3 py-1.5 bg-indigo-600/80 hover:bg-indigo-600 disabled:opacity-50 text-white text-xs rounded-lg transition-colors font-medium"
                        >
                          {actionLoading === rec.item_id ? '…' : 'Apply'}
                        </button>
                      )}
                    </td>
                  </motion.tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </motion.div>

      {s.items_below_margin_floor > 0 && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.5 }}
          className="rounded-xl border border-red-500/20 bg-red-500/5 p-4 flex items-start space-x-3">
          <AlertTriangle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
          <div>
            <p className="text-red-300 font-medium">{s.items_below_margin_floor} items below the 40% margin floor</p>
            <p className="text-red-400/70 text-sm mt-0.5">These items are selling at a loss or near-loss. Repricing is strongly recommended.</p>
          </div>
        </motion.div>
      )}
    </div>
  );
}
