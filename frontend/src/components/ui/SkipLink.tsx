"use client";

/**
 * SkipLink — keyboard-accessible "Skip to main content" anchor (WebAIM
 * keyboard-navigation pattern). Visually hidden until focused, then appears
 * as a small bar at the top-left so Tab users can jump past the sidebar nav
 * straight to page content. The target <main> must carry id="main-content".
 */
export default function SkipLink() {
    return (
        <a
            href="#main-content"
            className="sr-only focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-[100] focus:px-3 focus:py-2 focus:rounded-lg focus:bg-[var(--surface)] focus:border focus:border-[var(--accent)] focus:text-sm focus:text-[var(--text)]"
        >
            Skip to main content
        </a>
    );
}
