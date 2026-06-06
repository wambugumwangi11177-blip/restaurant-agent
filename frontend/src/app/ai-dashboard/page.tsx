"use client";

import React from 'react';
import { motion } from 'framer-motion';
import { Activity, Brain, ShieldCheck, Zap } from 'lucide-react';
import { MetricCard } from '@/components/ai/MetricCard';

export default function AIDashboardCommandCenter() {
  return (
    <div className="p-8 max-w-7xl mx-auto">
      <div className="mb-10">
        <motion.h1 
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          className="text-3xl font-bold text-zinc-900 dark:text-white tracking-tight mb-2"
        >
          AI Command Center
        </motion.h1>
        <motion.p 
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.1 }}
          className="text-zinc-500 dark:text-zinc-400"
        >
          Real-time overview of your autonomous restaurant agents.
        </motion.p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-12">
        <MetricCard
          title="Predicted Daily Revenue"
          value="KES 142k"
          change={12}
          trend="up"
          icon={<TrendingUpIcon />}
          delay={0.1}
        />
        <MetricCard
          title="Active Agents"
          value="7 / 15"
          icon={<Brain className="w-6 h-6" />}
          delay={0.2}
        />
        <MetricCard
          title="Pending Actions"
          value="4"
          icon={<Activity className="w-6 h-6" />}
          delay={0.3}
        />
        <MetricCard
          title="System Governance"
          value="Secure"
          icon={<ShieldCheck className="w-6 h-6" />}
          delay={0.4}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.5 }}
          className="bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-2xl p-6 shadow-sm"
        >
          <h3 className="text-lg font-bold text-zinc-900 dark:text-white mb-4 flex items-center">
            <Zap className="w-5 h-5 mr-2 text-yellow-500" />
            Recent AI Actions (Audit Log)
          </h3>
          <div className="space-y-4">
            {[
              { action: "Price increased for 'Beef Burger'", agent: "Pricing Intelligence", time: "10 mins ago" },
              { action: "Reorder: 10kg Tomatoes", agent: "Supply Chain", time: "1 hour ago" },
              { action: "Shift adjusted for John Doe", agent: "Labor Optimizer", time: "2 hours ago" },
            ].map((log, i) => (
              <div key={i} className="flex justify-between items-center pb-4 border-b border-zinc-100 dark:border-zinc-800 last:border-0 last:pb-0">
                <div>
                  <p className="font-medium text-sm text-zinc-900 dark:text-zinc-100">{log.action}</p>
                  <p className="text-xs text-zinc-500">{log.agent}</p>
                </div>
                <span className="text-xs text-zinc-400 bg-zinc-100 dark:bg-zinc-800 px-2 py-1 rounded-md">{log.time}</span>
              </div>
            ))}
          </div>
        </motion.div>
      </div>
    </div>
  );
}

function TrendingUpIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="22 7 13.5 15.5 8.5 10.5 2 17"></polyline>
      <polyline points="16 7 22 7 22 13"></polyline>
    </svg>
  );
}
