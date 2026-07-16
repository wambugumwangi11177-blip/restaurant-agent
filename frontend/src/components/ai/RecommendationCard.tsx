"use client";

import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Check, X, ArrowRight, Zap, TrendingUp } from 'lucide-react';

interface RecommendationCardProps {
  id: string;
  type: 'SURGE' | 'REPRICE' | 'STIMULATE';
  itemName: string;
  currentPrice: number;
  suggestedPrice: number;
  monthlyImpact: number;
  reason: string;
  strength: number;
  onApprove: (id: string) => void;
  onReject: (id: string) => void;
  delay?: number;
}

export function RecommendationCard({
  id, type, itemName, currentPrice, suggestedPrice, monthlyImpact, reason, strength, onApprove, onReject, delay = 0
}: RecommendationCardProps) {
  const [isHovered, setIsHovered] = useState(false);

  const formatCurrency = (cents: number) => `KES ${(cents / 100).toLocaleString()}`;

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.95, height: 0, marginBottom: 0, overflow: 'hidden' }}
      transition={{ duration: 0.4, delay }}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      className="bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-2xl p-6 shadow-sm relative overflow-hidden"
    >
      {/* Background glow based on type */}
      <div className={`absolute -inset-1 opacity-20 blur-xl transition-all duration-500 ${isHovered ? 'scale-110' : 'scale-100'} ${
        type === 'SURGE' ? 'bg-orange-500' : type === 'STIMULATE' ? 'bg-blue-500' : 'bg-emerald-500'
      }`} />

      <div className="relative z-10">
        <div className="flex justify-between items-start mb-6">
          <div>
            <div className="flex items-center space-x-2 mb-2">
              <span className={`text-xs font-bold px-2 py-1 rounded-md uppercase tracking-wider ${
                type === 'SURGE' ? 'bg-orange-100 text-orange-700 dark:bg-orange-500/20 dark:text-orange-400' :
                type === 'STIMULATE' ? 'bg-blue-100 text-blue-700 dark:bg-blue-500/20 dark:text-blue-400' :
                'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-400'
              }`}>
                {type}
              </span>
              <span className="text-xs font-medium text-zinc-500 flex items-center">
                <Zap className="w-3 h-3 mr-1" />
                {strength}% Confidence
              </span>
            </div>
            <h3 className="text-xl font-bold text-zinc-900 dark:text-white">{itemName}</h3>
          </div>
          <div className="text-right">
            <div className="text-sm text-emerald-600 dark:text-emerald-400 font-semibold flex items-center justify-end">
              <TrendingUp className="w-4 h-4 mr-1" />
              +{formatCurrency(monthlyImpact)} /mo
            </div>
            <div className="text-xs text-zinc-500">Predicted Impact</div>
          </div>
        </div>

        <div className="flex items-center space-x-6 mb-6">
          <div>
            <div className="text-sm text-zinc-500 mb-1">Current Price</div>
            <div className="text-lg font-medium text-zinc-400 line-through">{formatCurrency(currentPrice)}</div>
          </div>
          <ArrowRight className="text-zinc-300 dark:text-zinc-700 mt-5" />
          <div>
            <div className="text-sm text-zinc-500 mb-1">Suggested Price</div>
            <div className="text-2xl font-bold text-zinc-900 dark:text-white">{formatCurrency(suggestedPrice)}</div>
          </div>
        </div>

        <p className="text-zinc-600 dark:text-zinc-400 text-sm mb-6 leading-relaxed bg-zinc-50 dark:bg-zinc-800/50 p-3 rounded-lg">
          "{reason}"
        </p>

        <div className="flex items-center space-x-3">
          <button
            onClick={() => onApprove(id)}
            className="flex-1 bg-zinc-900 dark:bg-white text-white dark:text-zinc-900 font-medium py-2.5 px-4 rounded-xl flex items-center justify-center space-x-2 hover:opacity-90 transition-opacity active:scale-[0.98]"
          >
            <Check className="w-5 h-5" />
            <span>Approve & Apply</span>
          </button>
          <button
            onClick={() => onReject(id)}
            className="p-2.5 text-zinc-500 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-500/10 rounded-xl transition-colors active:scale-[0.98]"
            title="Reject Recommendation"
            aria-label="Reject Recommendation"
          >
            <X className="w-5 h-5" />
          </button>
        </div>
      </div>
    </motion.div>
  );
}
