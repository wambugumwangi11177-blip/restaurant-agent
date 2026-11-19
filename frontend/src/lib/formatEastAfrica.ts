/** Africa/Nairobi display for store and owner copy. */
export function formatNairobiDateTime(iso: string | null | undefined): string {
  if (!iso) return "";
  const when = new Date(iso);
  if (Number.isNaN(when.getTime())) return "";
  return when.toLocaleString("en-KE", {
    timeZone: "Africa/Nairobi",
    dateStyle: "medium",
    timeStyle: "short",
  });
}