"use client";
import { useEffect, useState } from "react";
import ProtectedRoute from "@/components/ProtectedRoute";
import Header from "@/components/Header";
import DashboardNav from "@/components/DashboardNav";
import { useAuth } from "@/context/AuthContext";
import Link from "next/link";
import { Brain } from "lucide-react";

interface DashboardStats {
  orders_today: number;
  revenue_today: number;
  active_tables: number;
  pending_orders: number;
}

export default function DashboardPage() {
  const { token } = useAuth();
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!token) return;
    fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/v1/analytics/dashboard`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => r.json())
      .then((d) => { setStats(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, [token]);

  const fmt = (cents: number) => `KES ${(cents / 100).toLocaleString()}`;

  return (
    <ProtectedRoute>
      <div className="min-h-screen bg-gray-50">
        <Header />
        <DashboardNav />
        <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
            <div className="bg-white rounded-xl shadow p-6">
              <h3 className="text-lg font-semibold text-gray-800">Today&apos;s Orders</h3>
              <p className="text-3xl font-bold text-indigo-600 mt-2">
                {loading ? "…" : stats?.orders_today ?? 0}
              </p>
            </div>
            <div className="bg-white rounded-xl shadow p-6">
              <h3 className="text-lg font-semibold text-gray-800">Revenue Today</h3>
              <p className="text-3xl font-bold text-green-600 mt-2">
                {loading ? "…" : stats ? fmt(stats.revenue_today) : "KES 0"}
              </p>
            </div>
            <div className="bg-white rounded-xl shadow p-6">
              <h3 className="text-lg font-semibold text-gray-800">Active Tables</h3>
              <p className="text-3xl font-bold text-orange-600 mt-2">
                {loading ? "…" : stats?.active_tables ?? 0}
              </p>
            </div>
            <div className="bg-white rounded-xl shadow p-6">
              <h3 className="text-lg font-semibold text-gray-800">Pending Orders</h3>
              <p className="text-3xl font-bold text-red-600 mt-2">
                {loading ? "…" : stats?.pending_orders ?? 0}
              </p>
            </div>
          </div>

          {/* AI Dashboard Banner */}
          <Link href="/ai-dashboard" className="block">
            <div className="bg-gradient-to-r from-indigo-900 via-purple-900 to-indigo-900 rounded-xl p-6 flex items-center justify-between hover:opacity-90 transition-opacity cursor-pointer border border-indigo-700">
              <div className="flex items-center space-x-4">
                <div className="w-12 h-12 rounded-xl bg-indigo-500/20 flex items-center justify-center">
                  <Brain className="w-7 h-7 text-indigo-400" />
                </div>
                <div>
                  <h3 className="text-white font-bold text-lg">AI Command Center</h3>
                  <p className="text-indigo-300 text-sm">Pricing intelligence, labor optimization, and revenue forecasting — live</p>
                </div>
              </div>
              <span className="text-indigo-300 text-sm font-medium bg-indigo-500/20 px-4 py-2 rounded-lg">
                Open AI Dashboard →
              </span>
            </div>
          </Link>
        </main>
      </div>
    </ProtectedRoute>
  );
}
