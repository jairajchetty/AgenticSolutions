// The model menu's pure helpers (model picker spec §7). No DOM here.

export const OFFLINE_ID = "offline";
export const OFFLINE_LABEL = "Offline (scripted)";

// The choices the server allows this browser: Offline first, then the rest.
export function menuOptions(session) {
  const listed = Array.isArray(session?.models)
    ? session.models.filter((m) => m && typeof m.id === "string" && typeof m.label === "string")
    : [];
  const rest = listed.filter((m) => m.id !== OFFLINE_ID);
  const offline = listed.find((m) => m.id === OFFLINE_ID) ?? { id: OFFLINE_ID, label: OFFLINE_LABEL };
  return [offline, ...rest];
}

// The stored choice, if it is still listed; otherwise Offline.
export function rememberedChoice(stored, options) {
  return options.some((o) => o.id === stored) ? stored : OFFLINE_ID;
}

// The badge for the conversation on screen. `model` is {id, label} or null.
export function badgeText(model) {
  if (!model || model.id === OFFLINE_ID) return OFFLINE_LABEL;
  return `Live · ${model.label}`;
}
