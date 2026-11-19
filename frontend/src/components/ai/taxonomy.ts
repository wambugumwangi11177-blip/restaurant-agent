export type AlertClass = "critical" | "warning" | "opportunity" | "information";

export const CLASS_CHIP: Record<AlertClass, string> = {
    critical: "bg-danger/10 text-danger",
    warning: "bg-warning/10 text-warning",
    opportunity: "bg-success/10 text-success",
    information: "bg-info/10 text-info",
};

export const CLASS_LABEL: Record<AlertClass, string> = {
    critical: "Critical",
    warning: "Warning",
    opportunity: "Opportunity",
    information: "Info",
};