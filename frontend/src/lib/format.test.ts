import { describe, it, expect } from "vitest";
import { formatKES, formatKESCompact } from "./format";

describe("formatKES", () => {
    it("converts cents to whole KES", () => {
        expect(formatKES(50000)).toBe("KES 500");
    });

    it("returns KES 0 for null/undefined/0", () => {
        expect(formatKES(0)).toBe("KES 0");
        expect(formatKES(null)).toBe("KES 0");
        expect(formatKES(undefined)).toBe("KES 0");
    });
});

describe("formatKESCompact", () => {
    it("leaves small amounts uncompacted", () => {
        expect(formatKESCompact(50000)).toBe("KES 500");
    });

    it("compacts thousands with a k suffix", () => {
        expect(formatKESCompact(1_500_000)).toBe("KES 15.0k");
    });

    it("compacts millions with an M suffix", () => {
        expect(formatKESCompact(150_000_000)).toBe("KES 1.5M");
    });

    it("returns KES 0 for null/undefined/0", () => {
        expect(formatKESCompact(0)).toBe("KES 0");
        expect(formatKESCompact(null)).toBe("KES 0");
    });
});
