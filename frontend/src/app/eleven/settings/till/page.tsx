"use client";

import Link from "next/link";
import OwnerShell from "@/components/eleven/OwnerShell";
import PosEvidence from "@/components/eleven/PosEvidence";

export default function TillEvidencePage() {
  return <OwnerShell title="Till evidence">
    <Link href="/eleven/settings" className="mb-4 inline-flex min-h-11 items-center text-sm text-white underline">Back to settings</Link>
    <PosEvidence />
  </OwnerShell>;
}
