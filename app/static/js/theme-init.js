// Runs before styles are loaded; the resolved theme is also available without storage.
(() => {
  let mode = "system";
  try {
    mode = localStorage.getItem("nutricoach_theme") || mode;
  } catch (_) {}
  if (!["light", "dark", "system"].includes(mode)) mode = "system";
  const dark =
    mode === "dark" ||
    (mode === "system" && matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.dataset.theme = dark ? "dark" : "light";
  document.documentElement.dataset.themeSetting = mode;
})();
