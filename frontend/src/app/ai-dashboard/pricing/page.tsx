"use client";

import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { RecommendationCard } from '@/components/ai/RecommendationCard';

export default function PricingIntelligence() {
  const [recommendations, setRecommendations] = useState([
    {
      id: "1",
      type: "SURGE" as const,
      itemName: "Spicy Beef Burger",
      currentPrice: 85000,
      suggestedPrice: 95000,
      monthlyImpact: 1200000,
      reason: "High demand detected during lunch hours. Stock levels of beef are sufficient to absorb slight drop in volume while maximizing margins.",
      strength: 94
    },
    {
      id: "2",
      type: "STIMULATE" as const,
      itemName: "Iced Caramel Latte",
      currentPrice: 40000,
      suggestedPrice: 35000,
      monthlyImpact: 450000,
      reason: "Historical data indicates lowering price by 12% on slow afternoons increases overall beverage volume by 25%.",
      strength: 88
    }
  ]);

  const handleApprove = (id: string) => {
    setRecommendations(prev => prev.filter(r => r.id !== id));
    // In a real app, this would make an API call to approve the DB recommendation
  };

  const handleReject = (id: string) => {
    setRecommendations(prev => prev.filter(r => r.id !== id));
    // In a real app, this would make an API call to reject
  };

  return (
    <div className="p-8 max-w-5xl mx-auto">
      <div className="mb-10">
        <motion.h1 
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          className="text-3xl font-bold text-zinc-900 dark:text-white tracking-tight mb-2"
        >
          Pricing Intelligence
        </motion.h1>
        <motion.p 
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.1 }}
          className="text-zinc-500 dark:text-zinc-400"
        >
          Review and approve AI-generated dynamic pricing recommendations.
        </motion.p>
      </div>

      <div className="space-y-6">
        <AnimatePresence>
          {recommendations.length === 0 ? (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="text-center py-20 bg-zinc-50 dark:bg-zinc-900/50 rounded-2xl border border-zinc-200/50 dark:border-zinc-800/50"
            >
              <div className="text-zinc-400 mb-2">✨ All caught up</div>
              <p className="text-zinc-500 text-sm">No pending pricing recommendations at the moment.</p>
            </motion.div>
          ) : (
            recommendations.map((rec, i) => (
              <RecommendationCard
                key={rec.id}
                {...rec}
                onApprove={handleApprove}
                onReject={handleReject}
                delay={i * 0.1}
              />
            ))
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
