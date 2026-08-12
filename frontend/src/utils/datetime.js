/** Asia/Kolkata (IST) — keep all user-visible timestamps consistent. */
export const APP_TIMEZONE = "Asia/Kolkata";

/**
 * Format an ISO/UTC timestamp for display in IST.
 * @param {string | number | Date | null | undefined} value
 * @returns {string}
 */
export function formatIstDateTime(value) {
  if (!value) {
    return "—";
  }
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "—";
  }
  return date.toLocaleString("en-IN", {
    timeZone: APP_TIMEZONE,
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: true
  });
}
