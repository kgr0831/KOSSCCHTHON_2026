// Next stores the initial query inside its history tree as well as the address bar.
// Preserve routing structure while removing auth credentials from both locations.
export function clearAuthLocation(path: "/auth/callback" | "/auth/confirm" | "/github/callback") {
  const clean = (value: unknown, key = ""): unknown => {
    if (key === "renderedSearch") return "";
    if (typeof value === "string" && value.startsWith("__PAGE__?")) return "__PAGE__";
    if (Array.isArray(value)) return value.map(item => clean(item));
    if (value && typeof value === "object") return Object.fromEntries(Object.entries(value).map(([name, item]) => [name, clean(item, name)]));
    return value;
  };
  window.history.replaceState(clean(window.history.state), "", path);
}
