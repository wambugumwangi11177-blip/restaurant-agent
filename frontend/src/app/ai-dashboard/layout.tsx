"use client";

import React from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { LayoutDashboard, Brain, Users, TrendingUp, ChevronLeft } from 'lucide-react';

export default function AIDashboardLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  const navItems = [
    { name: 'Command Center', href: '/ai-dashboard', icon: <LayoutDashboard className="w-5 h-5" /> },
    { name: 'Pricing Intelligence', href: '/ai-dashboard/pricing', icon: <TrendingUp className="w-5 h-5" /> },
    { name: 'Labor Optimization', href: '/ai-dashboard/labor', icon: <Users className="w-5 h-5" /> },
  ];

  return (
    <div className="flex h-screen bg-zinc-50 dark:bg-zinc-950">
      {/* Isolated AI Sidebar */}
      <aside className="w-64 bg-white dark:bg-zinc-900 border-r border-zinc-200 dark:border-zinc-800 flex flex-col">
        <div className="p-6 border-b border-zinc-200 dark:border-zinc-800">
          <div className="flex items-center space-x-2 text-indigo-600 dark:text-indigo-400 mb-6">
            <Brain className="w-8 h-8" />
            <span className="text-xl font-bold tracking-tight">AI Engine</span>
          </div>
          <Link href="/dashboard" className="flex items-center text-sm text-zinc-500 hover:text-zinc-900 dark:hover:text-white transition-colors">
            <ChevronLeft className="w-4 h-4 mr-1" />
            Back to Main App
          </Link>
        </div>

        <nav className="flex-1 p-4 space-y-1">
          {navItems.map((item) => {
            const isActive = pathname === item.href;
            return (
              <Link
                key={item.name}
                href={item.href}
                className={`flex items-center space-x-3 px-4 py-3 rounded-xl transition-all duration-200 ${
                  isActive 
                    ? 'bg-indigo-50 text-indigo-600 dark:bg-indigo-500/10 dark:text-indigo-400 font-medium' 
                    : 'text-zinc-600 hover:bg-zinc-100 dark:text-zinc-400 dark:hover:bg-zinc-800/50'
                }`}
              >
                {item.icon}
                <span>{item.name}</span>
              </Link>
            );
          })}
        </nav>
      </aside>

      {/* Main Content Area */}
      <main className="flex-1 overflow-y-auto">
        {children}
      </main>
    </div>
  );
}
