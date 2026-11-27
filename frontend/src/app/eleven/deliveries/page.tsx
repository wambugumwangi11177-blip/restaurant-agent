"use client";

import OwnerShell from "@/components/eleven/OwnerShell";
import { SectionLabel } from "@/components/eleven/EmptyPanels";
import DeliveryPriceConfirm from "@/components/store/DeliveryPriceConfirm";

export default function OwnerDeliveriesPage() {
  return (
    <OwnerShell title="Deliveries">
      <SectionLabel>What came in</SectionLabel>
      <DeliveryPriceConfirm />
    </OwnerShell>
  );
}