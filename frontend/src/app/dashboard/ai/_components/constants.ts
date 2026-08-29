// The Star/Plowhorse/Puzzle/Dog quadrants explained in plain language, so a
// non-analyst owner understands what the classification means and what to do.
export const MENU_CLASS = {
    Stars: { tone: "ok" as const, blurb: "Popular AND high-margin — your winners. Keep them prominent and never 86 them." },
    Plowhorses: { tone: undefined, blurb: "Popular but low-margin. Nudge price up or trim portion cost — small changes, big impact." },
    Puzzles: { tone: undefined, blurb: "High-margin but under-ordered. Promote, reposition on the menu, or add to upsell prompts." },
    Dogs: { tone: "warn" as const, blurb: "Low popularity and low margin. Rework the recipe or remove to free up menu space." },
};
