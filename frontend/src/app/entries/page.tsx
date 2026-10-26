"use client";
import EntryWorkspace from "@/components/operations/EntryWorkspace";
import OwnerShell from "@/components/owner/OwnerShell";
import { useAuth } from "@/context/AuthContext";
import { isOwnerAccount } from "@/lib/tenantHome";
import {useListQuery} from '@/lib/owner/useListQuery';
export default function EntriesPage(){const {user,isLoading}=useAuth();const [tool]=useListQuery('tool');if(isLoading)return <p role="status">Checking access…</p>;return isOwnerAccount(user)?<OwnerShell><div className="leviii-entry-shell"><EntryWorkspace key={tool}/></div></OwnerShell>:<main className="min-h-screen bg-slate-50 py-4"><EntryWorkspace key={tool}/></main>;}
