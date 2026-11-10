import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";

export function flexibleAgentUi(mobile) {
  for (const locale of ["en", "ar"])
    test(`${locale}: ${mobile ? "native" : "Web"} general creation and editable market defaults`, async ({
      page,
      context,
    }) => {
      test.setTimeout(60000);
      const fixture = (data) =>
        JSON.parse(
          execFileSync(".venv/bin/python", ["tests/check_chart_browser.py"], {
            input: JSON.stringify(data),
            encoding: "utf8",
          }),
        );
      const data = fixture({ action: "init", empty: true });
      const created = [];
      const name = `Flexible UI ${randomUUID()}`;
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
      const headers = {
        "X-CSRF-Token": data.cookies.find((cookie) => cookie.name === "lonora_csrf").value,
      };
      const errors = [];
      page.on("pageerror", (error) => errors.push(error.message));
      const read = async (id) => (await context.request.get(`/api/agents/${id}`)).json();
      try {
        if (mobile) await page.goto("/new");
        else {
          await page.goto("/app/");
          await page
            .getByRole("button", {
              name: locale === "ar" ? "محادثة جديدة" : "New chat",
              exact: true,
            })
            .first()
            .click();
          await page
            .locator("#dialog")
            .getByRole("button", { name: locale === "ar" ? /^وكيل جديد/ : /^New agent/ })
            .click();
          await expect(page).toHaveURL(/\/app\/new-agent$/);
        }
        const surface = mobile ? page : page.locator("main");
        // Owner decision Q9: the general template is chosen first, then named (Web and native).
        if (mobile)
          await expect(page.getByTestId("template-general")).toHaveAttribute(
            "aria-checked",
            "true",
          );
        else
          await expect(
            surface.getByRole("radio", { name: locale === "ar" ? /^وكيل عام/ : /^General agent/ }),
          ).toBeChecked();
        await surface.getByRole("button", { name: locale === "ar" ? "التالي" : "Next" }).click();
        await surface
          .getByLabel(locale === "ar" ? "اسم الوكيل" : "Agent name", { exact: true })
          .fill(name);
        await surface
          .getByLabel(locale === "ar" ? "الوصف" : "Description", { exact: true })
          .fill("Flexible general agent");
        const creation = page.waitForResponse(
          (response) =>
            new URL(response.url()).pathname === "/api/agents/create" &&
            response.request().method() === "POST",
        );
        await surface
          .getByRole("button", {
            name: locale === "ar" ? "إنشاء الوكيل" : "Create the agent",
            exact: true,
          })
          .click();
        const response = await creation;
        expect(response.status()).toBe(201);
        const agent = await response.json();
        created.push(agent.id);
        expect(agent.template).toBe("general");
        expect(agent.role).toBe("general");
        expect(agent.trading_account_id).toBeNull();
        expect(agent.trading_symbol).toBeNull();
        expect(agent.scope_mode).toBe("flexible");

        // Load an actual persisted market default, then remove it through the
        // settings UI. This exercises PATCH and explicit null semantics.
        const assigned = await context.request.patch(`/api/agents/${agent.id}`, {
          headers,
          data: {
            scope_mode: "flexible",
            trading_account_id: data.account,
            trading_symbol: data.symbol,
            expected_scope_revision: 0,
          },
        });
        expect(assigned.ok()).toBeTruthy();
        if (mobile) await page.goto(`/bot-settings?botId=${agent.id}`);
        else {
          await page.goto(`/app/${agent.id}`);
          await page
            .getByRole("button", {
              name: locale === "ar" ? "معلومات الوكيل" : "Agent info",
              exact: true,
            })
            .click();
        }
        const settings = mobile ? page : page.locator("#dialog");
        if (mobile)
          await expect(page.getByTestId("agent-market-mode-market-native")).toContainText(
            locale === "ar" ? "نشط" : "Active",
          );
        else await expect(page.getByTestId("agent-market-mode")).toHaveValue("market");
        if (mobile) await page.getByTestId("agent-market-mode-general-native").click();
        else await page.getByTestId("agent-market-mode").selectOption("general");
        await settings
          .getByRole("button", { name: locale === "ar" ? "حفظ" : "Save", exact: true })
          .click();
        await expect.poll(async () => (await read(agent.id)).trading_symbol).toBeNull();
        expect((await read(agent.id)).scope_revision).toBe(2);
        await page.reload();
        if (mobile)
          await expect(page.getByTestId("agent-market-mode-general-native")).toContainText(
            locale === "ar" ? "نشط" : "Active",
          );
        expect(errors).toEqual([]);
        expect(
          await page.evaluate(
            () => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1,
          ),
        ).toBeTruthy();
      } finally {
        for (const id of created) await context.request.delete(`/api/agents/${id}`, { headers });
        fixture({ ...data, action: "cleanup" });
      }
    });
}
