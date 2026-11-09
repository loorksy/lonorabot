import { execFileSync } from "node:child_process";
import { expect, test } from "@playwright/test";

export function homeToolbarUi(mobile) {
  for (const locale of ["en", "ar"])
    test(`${locale}: home has top search and create without settings or a visible conversations heading`, async ({
      page,
      context,
    }) => {
      test.setTimeout(60000);
      const fixture = (input) =>
        JSON.parse(
          execFileSync(".venv/bin/python", ["tests/check_chart_browser.py"], {
            input: JSON.stringify(input),
            encoding: "utf8",
          }),
        );
      const data = fixture({ action: "init", empty: true });
      await context.addCookies(
        data.cookies.map((cookie) => ({
          ...cookie,
          url: test.info().project.use.baseURL,
          httpOnly: cookie.name === "lonora_session",
          sameSite: "Strict",
        })),
      );
      await context.addInitScript(
        (language) => localStorage.setItem("lonora.locale", language),
        locale,
      );
      await page.setViewportSize({ width: 390, height: 844 });
      try {
        await page.goto(mobile ? "/" : "/app/");
        const surface = mobile ? page : page.locator(".topbar header.chats-header");
        // Web: the reference's chats header is the «Lonora» title, the search field and «+»; no settings there.
        const search = mobile
          ? surface.getByRole("button", {
              name: locale === "ar" ? "ابحث عن وكيل أو مجموعة" : "Search agents or groups",
              exact: true,
            })
          : surface.getByRole("searchbox", {
              name: locale === "ar" ? "بحث في Lonora" : "Search in Lonora",
              exact: true,
            });
        await expect(search).toBeVisible();
        await expect(
          surface.getByRole("button", {
            name: locale === "ar" ? "الإعدادات" : "Settings",
            exact: true,
          }),
        ).toHaveCount(0);
        await expect(
          page.getByRole("heading", {
            name: locale === "ar" ? "المحادثات" : "Conversations",
            exact: true,
          }),
        ).toHaveCount(0);
        await search.click();
        const field = mobile
          ? page.getByPlaceholder(
              locale === "ar" ? "ابحث عن وكيل أو مجموعة" : "Search agents or groups",
              { exact: true },
            )
          : search;
        await expect(field).toBeVisible();
        if (!mobile) await expect(surface).toHaveClass(/search-active/);
        await field.fill("no-match-visual-regression");
        if (!mobile) await expect(page.locator("[data-inbox-agent-id]")).toHaveCount(0);
        await field.fill("");
        if (mobile) {
          await search.click();
          await expect(field).not.toBeVisible();
        } else {
          await page.keyboard.press("Escape");
          await expect(surface).not.toHaveClass(/search-active/);
        }
        const create = surface.getByRole("button", {
          name:
            locale === "ar" ? (mobile ? "إنشاء" : "محادثة جديدة") : mobile ? "Create" : "New chat",
          exact: true,
        });
        await expect(create).toBeVisible();
        await page.screenshot({
          path: `.runtime/home-toolbar-${mobile ? "native" : "web"}-${locale}.png`,
          animations: "disabled",
        });
        await create.click();
        await expect(
          page.getByRole("button", { name: locale === "ar" ? /^وكيل جديد/ : /^New agent/ }),
        ).toBeVisible();
      } finally {
        fixture({ ...data, action: "cleanup" });
      }
    });
}
