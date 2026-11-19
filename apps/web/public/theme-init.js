// Apply saved appearance before styles and React paint the first frame.
(() => {
  const root = document.documentElement;
  try {
    const theme = JSON.parse(localStorage.getItem("lonora.theme") ?? '"dark"');
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
