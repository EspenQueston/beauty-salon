const EVENTS = new Set(["NETWORK_STATE_CHANGED", "INIT_WIDGET", "WIDGET_SUCCESSFULLY_INIT",
  "CLOSE_WIDGET", "DESTROY_WIDGET", "WIDGET_SUCCESSFULLY_DESTROYED", "PAYMENT_INIT",
  "PAYMENT_ABORTED", "PENDING_PAYMENT", "ON_USER_FEEDBACK", "PAYMENT_FAILED",
  "PAYMENT_SUCCESS", "PAYMENT_END", "RETRY_PAYMENT", "WAVE_LINK"]);

export function messageKkiapayRejete(event, cadre) {
  if (!event.data || !EVENTS.has(event.data.name)) return false;
  return !cadre || event.origin !== "https://widget-v3.kkiapay.me" ||
    event.source !== cadre.contentWindow || event.data.name === "WAVE_LINK";
}
