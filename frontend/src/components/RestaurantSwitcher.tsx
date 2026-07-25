"use client";

import { useEffect, useState } from "react";
import { Store } from "lucide-react";
import api from "@/lib/api";

interface Restaurant {
    id: number;
    name: string;
    address: string | null;
    is_active: boolean;
}

/**
 * Audit remediation, Tier 5 item 11 — a chain owner previously had no way to
 * pick which of their restaurants they were managing; every request silently
 * resolved to the tenant's first one. Owner-only (matches the backend's
 * require_role(ADMIN) gate on GET/POST /restaurants) and renders nothing for
 * the overwhelming majority of tenants with a single restaurant — only a
 * 403 or a one-item list ever comes back for anyone else, both handled by
 * simply not rendering.
 */
export default function RestaurantSwitcher() {
    const [restaurants, setRestaurants] = useState<Restaurant[]>([]);
    const [switching, setSwitching] = useState(false);

    useEffect(() => {
        api.get("/restaurants/").then((res) => {
            setRestaurants(res.data);
        }).catch(() => {
            // 403 for non-Owner accounts, or the route simply not mattering
            // yet — either way, nothing to show.
        });
    }, []);

    if (restaurants.length <= 1) return null;

    const active = restaurants.find((r) => r.is_active);

    const handleSwitch = async (restaurantId: number) => {
        if (restaurantId === active?.id) return;
        setSwitching(true);
        try {
            await api.post("/restaurants/select", { restaurant_id: restaurantId });
            // Full reload rather than local state — every dashboard section
            // fetches its own data scoped to "the" restaurant server-side;
            // a reload is the simplest way to guarantee everything (menu,
            // orders, staff, AI insights, …) refetches under the new one.
            window.location.reload();
        } catch {
            setSwitching(false);
        }
    };

    return (
        <div className="flex items-center gap-1.5">
            <Store className="w-3.5 h-3.5 text-[#525252]" />
            <select
                aria-label="Switch restaurant"
                value={active?.id ?? ""}
                disabled={switching}
                onChange={(e) => handleSwitch(Number(e.target.value))}
                className="bg-transparent text-xs text-[#e5e5e5] border border-[#262626] rounded-lg px-2 py-1 focus:outline-none focus:border-[var(--accent)] disabled:opacity-60"
            >
                {restaurants.map((r) => (
                    <option key={r.id} value={r.id} className="bg-[#0f0f0f]">
                        {r.name}
                    </option>
                ))}
            </select>
        </div>
    );
}
