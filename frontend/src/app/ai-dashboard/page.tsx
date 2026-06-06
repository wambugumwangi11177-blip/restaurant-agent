"use client";

import React, { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { Activity, Brain, ShieldCheck, Zap, TrendingUp, AlertTriangle, CheckCircle, RefreshCw } from 'lucide-react';
import { MetricCard } from '@/components/ai/MetricCard';
import { useAuth } from '@/context/AuthContext';

interface DashboardData {
  health_score: number;
  health_breakdown: { category: string; score: number; weight: number; detail: string }[];
  quick_stats: {
    today_orders: number;
    revenue_today_kes: string;
    total_revenue_30d_kes: string;
    avg_daily_revenue_kes: string;
    pending_orders: number;
    active_alerts: number;
    week_over_week_growth: number;
  };
  risks: { severity: string; risk: string; detail: string }[];
  opportunities: { opportunity: string; potential: string; agent: string }[];
  recent_ai_actions: { action: string; agent: string; time: string }[];
  restaurant: { name: string };
}

export default function AIDashboardCommandCenter() {
  const { token } = useAuth();
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const fetchData = async () => {
    if (!token) return;
    setLoading(true);
    setError('');
    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/ai/dashboard`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error(`API error: ${res.status}`);
      const json = await res.json();
      setData(json);
      setLastUpdated(new Date());
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchData(); }, [token]);

  const healthColor = (score: number) =>
    score >= 75 ? 'text-emerald-400' : score >= 50 ? 'text-amber-400' : 'text-red-400';

  const healthBorder = (score: number) =>
    score >= 75 ? 'border-emerald-400/40' : score >= 50 ? 'border-amber-400/40' : 'border-red-400/40';

  const severityColor = (s: string) => ({
    CRITICAL: 'text-red-400 bg-red-500/10 border-red-500/20',
    HIGH: 'text-orange-400 bg-orange-500/10 border-orange-500/20',
    MEDIUM: 'text-amber-400 bg-amber-500/10 border-amber-500/20',
  }[s] || 'text-blue-400 bg-blue-500/10 border-blue-500/20');

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] space-y-4">
        <div className="w-16 h-16 border-4 border-indigo-500/30 border-t-indigo-400 rounded-full animate-spin" />
        <p className="text-slate-400 text-sm animate-pulse">Loading AI intelligence…</p>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] space-y-4">
        <AlertTriangle className="w-12 h-12 text-amber-400" />
        <p className="text-slate-300 font-medium">Could not load AI data</p>
        <p className="text-slate-500 text-sm max-w-md text-center">{error || 'Unknown error'}</p>
        <button onClick={fetchData} className="px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm hover:bg-indigo-700 transition-colors">
          Retry
        </button>
      </div>
    );
  }

  const hs = data.health_score;
  const qs = data.quick_stats;

  return (
    <div className="space-y-8">
      {/* Header */}
      <motion.div initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }} className="flex items-start justify-between">
        <div>
          <h1 className="text-3xl font-bold text-white tracking-tight">AI Command Center</h1>
          <p className="text-slate-400 mt-1">
            {data.restaurant.name} — Real-time intelligence across all operations
          </p>
        </div>
        <button
          onClick={fetchData}
          className="flex items-center space-x-2 px-3 py-2 rounded-lg bg-white/5 border border-white/10 text-slate-400 hover:text-white hover:bg-white/10 transition-all text-sm"
        >
          <RefreshCw className="w-4 h-4" />
          <span>{lastUpdated ? `Updated ${lastUpdated.toLocaleTimeString()}` : 'Refresh'}</span>
        </button>
      </motion.div>

      {/* Health Score Card */}
      <motion.div
        initial={{ opacity: 0, scale: 0.97 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ delay: 0.1 }}
        className={`rounded-2xl border ${healthBorder(hs)} bg-white/5 backdrop-blur-md p-8`}
      >
        <div className="flex items-center justify-between">
          <div>
            <p className="text-slate-400 text-sm uppercase tracking-widest mb-1">System Health Score</p>
            <p className={`text-7xl font-black ${healthColor(hs)}`}>{hs}</p>
            <p className="text-slate-500 text-sm mt-2">
              WoW Revenue: <span className={qs.week_over_week_growth >= 0 ? 'text-emerald-400' : 'text-red-400'}>
                {qs.week_over_week_growth >= 0 ? '+' : ''}{qs.week_over_week_growth}%
              </span>
            </p>
          </div>
          <div className="space-y-2 min-w-[200px]">
            {data.health_breakdown.map((b, i) => (
              <div key={i}>
                <div className="flex justify-between text-xs text-slate-400 mb-1">
                  <span>{b.category}</span>
                  <span>{b.score}/100</span>
                </div>
                <div className="w-full bg-white/10 rounded-full h-1.5">
                  <div
                    className={`h-1.5 rounded-full transition-all ${b.score >= 70 ? 'bg-emerald-400' : b.score >= 50 ? 'bg-amber-400' : 'bg-red-400'}`}
                    style={{ width: `${b.score}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
      </motion.div>

      {/* Metric Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard title="Revenue Today" value={qs.revenue_today_kes} change={qs.week_over_week_growth} trend={qs.week_over_week_growth >= 0 ? 'up' : 'down'} icon={<TrendingUp className="w-5 h-5" />} delay={0.2} />
        <MetricCard title="Orders Today" value={String(qs.today_orders)} icon={<Activity className="w-5 h-5" />} delay={0.25} />
        <MetricCard title="Active Alerts" value={String(qs.active_alerts)} trend={qs.active_alerts > 0 ? 'down' : 'up'} icon={<AlertTriangle className="w-5 h-5" />} delay={0.3} />
        <MetricCard title="System Status" value={hs >= 70 ? 'Healthy' : hs >= 50 ? 'Warning' : 'Critical'} icon={<ShieldCheck className="w-5 h-5" />} delay={0.35} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Risks */}
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.4 }}
          className="rounded-2xl border border-white/10 bg-white/5 backdrop-blur-md p-6">
          <h2 className="text-lg font-semibold text-white mb-4 flex items-center space-x-2">
            <AlertTriangle className="w-5 h-5 text-red-400" />
            <span>Active Risks ({data.risks.length})</span>
          </h2>
          {data.risks.length === 0 ? (
            <div className="flex items-center space-x-2 text-emerald-400 py-4">
              <CheckCircle className="w-5 h-5" />
              <span className="text-sm">No active risks — system healthy</span>
            </div>
          ) : (
            <div className="space-y-3">
              {data.risks.map((r, i) => (
                <div key={i} className={`p-3 rounded-xl border ${severityColor(r.severity)}`}>
                  <div className="flex items-center space-x-2 mb-1">
                    <span className="text-xs font-bold uppercase tracking-wider">{r.severity}</span>
                  </div>
                  <p className="font-medium text-sm text-white">{r.risk}</p>
                  <p className="text-xs opacity-70 mt-0.5">{r.detail}</p>
                </div>
              ))}
            </div>
          )}
        </motion.div>

        {/* Opportunities + Recent Actions */}
        <div className="space-y-6">
          {data.opportunities.length > 0 && (
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.45 }}
              className="rounded-2xl border border-emerald-500/20 bg-emerald-500/5 backdrop-blur-md p-6">
              <h2 className="text-lg font-semibold text-white mb-4 flex items-center space-x-2">
                <TrendingUp className="w-5 h-5 text-emerald-400" />
                <span>Opportunities</span>
              </h2>
              <div className="space-y-3">
                {data.opportunities.map((o, i) => (
                  <div key={i} className="p-3 rounded-xl bg-white/5 border border-white/5">
                    <p className="font-medium text-white text-sm">{o.opportunity}</p>
                    <p className="text-emerald-400 text-sm font-medium mt-0.5">{o.potential}</p>
                    <p className="text-slate-500 text-xs mt-0.5">{o.agent}</p>
                  </div>
                ))}
              </div>
            </motion.div>
          )}

          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.5 }}
            className="rounded-2xl border border-white/10 bg-white/5 backdrop-blur-md p-6">
            <h2 className="text-lg font-semibold text-white mb-4 flex items-center space-x-2">
              <Zap className="w-5 h-5 text-yellow-400" />
              <span>Recent AI Actions</span>
            </h2>
            {data.recent_ai_actions.length === 0 ? (
              <p className="text-slate-500 text-sm py-2">No AI actions logged yet</p>
            ) : (
              <div className="space-y-3">
                {data.recent_ai_actions.map((log, i) => (
                  <div key={i} className="flex justify-between items-center pb-3 border-b border-white/5 last:border-0 last:pb-0">
                    <div>
                      <p className="font-medium text-sm text-white">{log.action}</p>
                      <p className="text-xs text-slate-500">{log.agent}</p>
                    </div>
                    <span className="text-xs text-slate-400 bg-white/5 px-2 py-1 rounded-md whitespace-nowrap">{log.time}</span>
                  </div>
                ))}
              </div>
            )}
          </motion.div>
        </div>
      </div>

      {/* 30-Day Revenue Summary */}
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.6 }}
        className="rounded-2xl border border-white/10 bg-white/5 backdrop-blur-md p-6">
        <h2 className="text-xl font-semibold text-white mb-4 flex items-center space-x-2">
          <Brain className="w-5 h-5 text-indigo-400" />
          <span>30-Day Performance</span>
        </h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[
            { label: 'Total Revenue (30d)', value: qs.total_revenue_30d_kes },
            { label: 'Avg Daily Revenue', value: qs.avg_daily_revenue_kes },
            { label: 'Pending Orders', value: String(qs.pending_orders) },
            { label: 'Active Alerts', value: String(qs.active_alerts) },
          ].map((stat, i) => (
            <div key={i} className="p-4 rounded-xl bg-white/5 border border-white/5 text-center">
              <p className="text-2xl font-bold text-white">{stat.value}</p>
              <p className="text-xs text-slate-400 mt-1">{stat.label}</p>
            </div>
          ))}
        </div>
      </motion.div>
    </div>
  );
}
