"use client";

import OwnerShell from "@/components/eleven/OwnerShell";
import { SalesLineBlock } from "@/components/eleven/v11/ChartBlocks";
import { useOwnerGet } from "@/hooks/useOwnerV11";

export default function SalesDetailPage() {
  const { data } = useOwnerGet("/api/v1/eleven/money/series/sales?days=90", []);
  return (
    <OwnerShell title="Sales detail">
      <SalesLineBlock data={data as never} />
    </OwnerShell>
  );
}