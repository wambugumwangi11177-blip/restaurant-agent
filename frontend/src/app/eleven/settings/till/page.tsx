"use client";

import Link from "next/link";
import OwnerShell from "@/components/eleven/OwnerShell";
import PosEvidence from "@/components/eleven/PosEvidence";
import { useAuth } from "@/context/AuthContext";

export default function TillEvidencePage() {
  const { user } = useAuth();
  return <OwnerShell title="Till evidence">
    <Link href="/eleven/settings" className="mb-4 inline-flex min-h-11 items-center text-sm text-white underline">Back to settings</Link>
    <PosEvidence key={`${user?.id}:${user?.restaurant_id}`} />
  </OwnerShell>;
}
