"use client";

import React from 'react';
import { motion } from 'framer-motion';
import { Clock, Users, UserCheck } from 'lucide-react';
import { MetricCard } from '@/components/ai/MetricCard';

export default function LaborOptimization() {
  return (
    <div className="p-8 max-w-7xl mx-auto">
      <div className="mb-10">
        <motion.h1 
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          className="text-3xl font-bold text-zinc-900 dark:text-white tracking-tight mb-2"
        >
          Labor Optimization
        </motion.h1>
        <motion.p 
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.1 }}
          className="text-zinc-500 dark:text-zinc-400"
        >
          AI insights on shift staffing, productivity, and labor cost efficiency.
        </motion.p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-10">
        <MetricCard
          title="Current Labor Cost %"
          value="24.2%"
          change={1.5}
          trend="down"
          icon={<Clock className="w-6 h-6" />}
          delay={0.1}
        />
        <MetricCard
          title="Optimal Shift Size (Tonight)"
          value="4 Servers"
          icon={<Users className="w-6 h-6" />}
          delay={0.2}
        />
        <MetricCard
          title="Productivity Score"
          value="92 / 100"
          change={5}
          trend="up"
          icon={<UserCheck className="w-6 h-6" />}
          delay={0.3}
        />
      </div>

      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.4 }}
        className="bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-2xl p-6 shadow-sm max-w-3xl"
      >
        <h3 className="text-lg font-bold text-zinc-900 dark:text-white mb-6">AI Shift Recommendations</h3>
        
        <div className="space-y-4">
          <div className="p-4 bg-emerald-50 dark:bg-emerald-500/10 border border-emerald-100 dark:border-emerald-500/20 rounded-xl">
            <h4 className="font-semibold text-emerald-800 dark:text-emerald-400 mb-1">Reduce Tuesday Morning Staffing</h4>
            <p className="text-sm text-emerald-600 dark:text-emerald-300">
              Historical foot traffic and weather forecasts predict a slow morning. Reducing back-of-house staff by 1 person from 8 AM - 12 PM will save KES 4,500 without impacting service times.
            </p>
          </div>

          <div className="p-4 bg-amber-50 dark:bg-amber-500/10 border border-amber-100 dark:border-amber-500/20 rounded-xl">
            <h4 className="font-semibold text-amber-800 dark:text-amber-400 mb-1">Surge Staffing Needed: Friday Evening</h4>
            <p className="text-sm text-amber-600 dark:text-amber-300">
              A local concert is scheduled nearby. Demand is projected to spike by 40% between 7 PM - 10 PM. Consider extending the mid-shift for 2 additional servers.
            </p>
          </div>
        </div>
      </motion.div>
    </div>
  );
}
