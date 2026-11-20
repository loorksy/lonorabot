// Apply saved appearance before styles and React paint the first frame. With no saved choice
// the first visit follows the device (prefers-color-scheme); a saved choice wins.
(() => {
  const root = document.documentElement;
  try {
    const saved = localStorage.getItem("lonora.theme");
    const theme =
      saved === null
        ? typeof matchMedia === "function" && matchMedia("(prefers-color-scheme: light)").matches
          ? "light"
          : "dark"
        : JSON.parse(saved);
    root.dataset.theme = theme === "light" ? "light" : "dark";
    root.classList.toggle("dark", root.dataset.theme === "dark");
    // The browser's own bar takes the page colour from the first frame (the reference's values).
    document
      .querySelector('meta[name="theme-color"]')
      ?.setAttribute("content", root.dataset.theme === "light" ? "#f7f5ef" : "#0b0c10");
    root.lang = localStorage.getItem("lonora.locale") === "en" ? "en" : "ar";
    root.dir = root.lang === "ar" ? "rtl" : "ltr";
  } catch {
    // The HTML defaults also work with blocked or corrupt browser storage.
  }
})();
