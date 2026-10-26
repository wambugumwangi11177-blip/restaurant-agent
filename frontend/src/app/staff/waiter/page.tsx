"use client";
import DailyWorkspace from '@/components/operations/DailyWorkspace';
import POSWorkspace from '@/components/features/pos/POSWorkspace';
export default function StaffHome(){return <div className="space-y-5"><DailyWorkspace/><details className="rounded-xl border p-4"><summary className="min-h-11 cursor-pointer py-2 font-semibold">Full sales workspace</summary><POSWorkspace/></details></div>;}
