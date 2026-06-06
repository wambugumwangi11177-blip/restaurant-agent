"use client";

import React, { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { Users, Clock, TrendingUp, AlertTriangle, RefreshCw, CheckCircle, BarChart2 } from 'lucide-react';
import { MetricCard } from '@/components/ai/MetricCard';
import { useAuth } from '@/context/AuthContext';

interface LaborSummary {
  total_labor_cost_30d: number;
  total_hours_30d: number;
  total_revenue_30d: number;
  labor_pct: number;
  labor_status: string;
  sales_per_hour: number;
  overtime_hours_30d: number;
  overtime_cost_30d: number;
  shifts_logged: number;
}

interface LaborRec {
  priority: string;
  message: string;
  action: string;
}

interface DailyEntry {
  date: string;
  day: string;
  labor_cost: number;
  hours: number;
  revenue: number;
  labor_pct: number;
}

interface LaborData {
  summary: LaborSummary;
  daily_breakdown: DailyEntry[];
  staff_productivity: { staff_name: string; hours_worked: number; labor_cost: number; est_revenue_generated: number; cost_pct_of_revenue: number }[];
  recommendations: LaborRec[];
}

const priorityStyle: Record<string, string> = {
  HIGH: 'border-red-500/30 bg-red-500/5 text-red-300',
  MEDIUM: 'border-amber-500/30 bg-amber-500/5 text-amber-300',
  INFO: 'border-blue-500/30 bg-blue-500/5 text-blue-300',
};

export default function LaborOptimization() {
  const { token } = useAuth();
  const [data, setData] = useState<LaborData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const fetchData = async () => {
    if (!token) return;
    setLoading(true);
    setError('');
    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/ai/labor`, {
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

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] space-y-4">
        <div className="w-16 h-16 border-4 border-indigo-500/30 border-t-indigo-400 rounded-full animate-spin" />
        <p className="text-slate-400 text-sm animate-pulse">Analysing labor data…</p>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] space-y-4">
        <AlertTriangle className="w-12 h-12 text-amber-400" />
        <p className="text-slate-300 font-medium">Could not load labor data</p>
        <p className="text-slate-500 text-sm">{error}</p>
        <button onClick={fetchData} className="px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm hover:bg-indigo-700">Retry</button>
      </div>
    );
  }

  const s = data.summary;
  const laborStatusColor = s.labor_status === 'HEALTHY' ? 'text-emerald-400' : s.labor_status === 'HIGH' ? 'text-red-400' : 'text-slate-400';
  const laborPctColor = s.labor_pct <= 30 ? 'bg-emerald-400' : s.labor_pct <= 40 ? 'bg-amber-400' : 'bg-red-400';

  return (
    <div className="space-y-8">
      <motion.div initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }} className="flex items-start justify-between">
        <div>
          <h1 className="text-3xl font-bold text-white">Labor Optimization</h1>
          <p className="text-slate-400 mt-1">
            {s.shifts_logged > 0
              ? `AI-driven insights from ${s.shifts_logged} shifts logged over 30 days`
              : 'Start logging shifts to unlock full labor intelligence'}
          </p>
        </div>
        <button onClick={fetchData} className="flex items-center space-x-2 px-3 py-2 rounded-lg bg-white/5 border border-white/10 text-slate-400 hover:text-white transition-all text-sm">
          <RefreshCw className="w-4 h-4" />
          <span>Refresh</span>
        </button>
      </motion.div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <MetricCard
          title="Labor Cost %"
          value={s.shifts_logged > 0 ? `${s.labor_pct}%` : 'No data'}
          trend={s.labor_pct <= 30 ? 'up' : 'down'}
          icon={<Users className="w-5 h-5" />}
          delay={0.1}
        />
        <MetricCard
          title="Total Hours (30d)"
          value={s.shifts_logged > 0 ? `${s.total_hours_30d}h` : '--'}
          icon={<Clock className="w-5 h-5" />}
          delay={0.15}
        />
        <MetricCard
          title="Sales / Hour"
          value={s.shifts_logged > 0 ? `KES ${(s.sales_per_hour / 100).toLocaleString()}` : '--'}
          trend="up"
          icon={<TrendingUp className="w-5 h-5" />}
          delay={0.2}
        />
        <MetricCard
          title="Overtime Hours"
          value={s.shifts_logged > 0 ? `${s.overtime_hours_30d}h` : '--'}
          trend={s.overtime_hours_30d > 20 ? 'down' : 'up'}
          icon={<Clock className="w-5 h-5" />}
          delay={0.25}
        />
      </div>

      {/* Labor Cost % Gauge */}
      {s.shifts_logged > 0 && (
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }}
          className="rounded-2xl border border-white/10 bg-white/5 backdrop-blur-md p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-white">Labor Cost Analysis</h2>
            <span className={`font-bold text-2xl ${laborStatusColor}`}>{s.labor_pct}%</span>
          </div>
          <div className="w-full bg-white/10 rounded-full h-4 mb-3">
            <div
              className={`h-4 rounded-full transition-all ${laborPctColor}`}
              style={{ width: `${Math.min(100, s.labor_pct)}%` }}
            />
          </div>
          <div className="flex justify-between text-xs text-slate-500">
            <span>0%</span>
            <span className="text-emerald-400 font-medium">Target ≤30%</span>
            <span>50%</span>
            <span>100%</span>
          </div>
          <div className="grid grid-cols-3 gap-4 mt-4">
            <div className="text-center p-3 rounded-xl bg-white/5">
              <p className="text-lg font-bold text-white">KES {(s.total_labor_cost_30d / 100).toLocaleString()}</p>
              <p className="text-xs text-slate-400">Total Labor Cost</p>
            </div>
            <div className="text-center p-3 rounded-xl bg-white/5">
              <p className="text-lg font-bold text-white">KES {(s.total_revenue_30d / 100).toLocaleString()}</p>
              <p className="text-xs text-slate-400">Total Revenue (30d)</p>
            </div>
            <div className="text-center p-3 rounded-xl bg-white/5">
              <p className="text-lg font-bold text-white">KES {(s.overtime_cost_30d / 100).toLocaleString()}</p>
              <p className="text-xs text-slate-400">Overtime Cost</p>
            </div>
          </div>
        </motion.div>
      )}

      {/* Recommendations */}
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.35 }}
        className="rounded-2xl border border-white/10 bg-white/5 backdrop-blur-md p-6">
        <h2 className="text-xl font-semibold text-white mb-4 flex items-center space-x-2">
          <BarChart2 className="w-5 h-5 text-indigo-400" />
          <span>AI Recommendations</span>
        </h2>
        {data.recommendations.length === 0 ? (
          <div className="flex items-center space-x-3 py-4 text-emerald-400">
            <CheckCircle className="w-5 h-5" />
            <p className="text-sm">Labor scheduling is optimised — no changes needed.</p>
          </div>
        ) : (
          <div className="space-y-3">
            {data.recommendations.map((rec, i) => (
              <motion.div key={i} initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.4 + i * 0.05 }}
                className={`p-4 rounded-xl border ${priorityStyle[rec.priority] || 'border-white/10 bg-white/5 text-slate-300'}`}>
                <div className="flex items-center space-x-2 mb-1">
                  <span className="text-xs font-bold uppercase tracking-wider opacity-70">{rec.priority}</span>
                </div>
                <p className="font-medium text-sm">{rec.message}</p>
                <p className="text-xs opacity-70 mt-1">💡 {rec.action}</p>
              </motion.div>
            ))}
          </div>
        )}
      </motion.div>

      {/* Daily Breakdown */}
      {data.daily_breakdown.length > 0 && (
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.4 }}
          className="rounded-2xl border border-white/10 bg-white/5 backdrop-blur-md p-6">
          <h2 className="text-xl font-semibold text-white mb-5">Daily Labor vs Revenue (Last 14 Days)</h2>
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead>
                <tr className="border-b border-white/10">
                  {['Date', 'Day', 'Revenue', 'Labor Cost', 'Hours', 'Labor %'].map(h => (
                    <th key={h} className="pb-3 text-slate-400 text-xs font-medium uppercase tracking-wider pr-4">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {data.daily_breakdown.slice(-14).reverse().map((day, i) => (
                  <tr key={i} className="hover:bg-white/5 transition-colors">
                    <td className="py-3 pr-4 text-slate-300 text-sm">{day.date}</td>
                    <td className="py-3 pr-4 text-white text-sm font-medium">{day.day}</td>
                    <td className="py-3 pr-4 text-emerald-400 text-sm">KES {(day.revenue / 100).toLocaleString()}</td>
                    <td className="py-3 pr-4 text-slate-300 text-sm">KES {(day.labor_cost / 100).toLocaleString()}</td>
                    <td className="py-3 pr-4 text-slate-300 text-sm">{day.hours}h</td>
                    <td className="py-3 pr-4">
                      <span className={`text-sm font-medium ${day.labor_pct <= 30 ? 'text-emerald-400' : day.labor_pct <= 40 ? 'text-amber-400' : 'text-red-400'}`}>
                        {day.labor_pct}%
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </motion.div>
      )}

      {/* Staff Productivity */}
      {data.staff_productivity.length > 0 && (
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.45 }}
          className="rounded-2xl border border-white/10 bg-white/5 backdrop-blur-md p-6">
          <h2 className="text-xl font-semibold text-white mb-5">Staff Productivity</h2>
          <div className="space-y-3">
            {data.staff_productivity.map((staff, i) => (
              <div key={i} className="flex items-center justify-between p-4 rounded-xl bg-white/5 border border-white/5">
                <div>
                  <p className="text-white font-medium">{staff.staff_name}</p>
                  <p className="text-slate-400 text-sm">{staff.hours_worked}h worked</p>
                </div>
                <div className="text-right">
                  <p className="text-emerald-400 text-sm font-medium">KES {(staff.est_revenue_generated / 100).toLocaleString()} generated</p>
                  <p className="text-slate-400 text-xs">Labor: {staff.cost_pct_of_revenue}% of revenue</p>
                </div>
              </div>
            ))}
          </div>
        </motion.div>
      )}
    </div>
  );
}
