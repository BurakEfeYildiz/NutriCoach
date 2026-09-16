/* Run only against scripts/ui_v2_preview.py. See docs/ui-v2.md. */
const { chromium, webkit } = require("playwright");
const { default: AxeBuilder } = require("@axe-core/playwright");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const BASE = "http://127.0.0.1:8766";
const output =
  process.env.UI_REVIEW_OUTPUT ||
  fs.mkdtempSync(path.join(os.tmpdir(), "nutricoach-ui-shots-"));
fs.mkdirSync(output, { recursive: true });
const widths = [390, 768, 1280];
const routes = ["today", "meals", "progress", "recipes", "profile", "account", "coach"];
(async () => {
  const marker = await fetch(BASE + "/ui-review-marker").then((r) => r.json());
  assert.equal(
    marker.isolated_ui_review,
    true,
    "Refusing to modify a non-review server",
  );
  const browserType = process.env.UI_BROWSER === "webkit" ? webkit : chromium;
  const browser = await browserType.launch(
    browserType === chromium && process.env.CHROME_PATH
      ? { executablePath: process.env.CHROME_PATH, headless: true }
      : { headless: true },
  );
  try {
    const context = await browser.newContext({
      viewport: { width: 1280, height: 960 },
      locale: "tr-TR",
      timezoneId: "Europe/Istanbul",
      colorScheme: "light",
    });
    const page = await context.newPage();
    const errors = [];
    page.on("pageerror", (e) => {
      errors.push(e.message);
      console.log("JS_ERROR", e.message);
    });
    const consoleErrors = [];
    const failedFirstParty = [];
    const badFirstPartyResponses = [];
    const noContentResponses = new Set();
    page.on("console", (m) => {
      if (m.type() === "error") consoleErrors.push(m.text());
    });
    page.on("requestfailed", (request) => {
      if (request.url().startsWith(BASE)) failedFirstParty.push({ method: request.method(), url: request.url(), currentPage: page.url(), failure: request.failure()?.errorText || null });
    });
    page.on("response", (response) => {
      if (response.url().startsWith(BASE) && response.status() === 204)
        noContentResponses.add(`${response.request().method()} ${response.url()}`);
      if (response.url().startsWith(BASE) &&
          (response.status() >= 500 ||
           (response.status() === 404 && response.url().includes("/static/")))) {
        badFirstPartyResponses.push(`${response.status()} ${response.url()}`);
      }
    });
    const audit = [];
    let checks = 0;
    async function noOverflow(label) {
      const dimensions = await page.evaluate(() => ({
        width: innerWidth,
        scroll: document.documentElement.scrollWidth,
      }));
      assert(
        dimensions.scroll <= dimensions.width,
        `${label}: ${JSON.stringify(dimensions)}`,
      );
      checks++;
    }
    async function screenshot(name) {
      await page.screenshot({
        path: path.join(output, name + ".png"),
        fullPage: true,
      });
    }
    async function gotoApp(route) {
      const endpoint = route === "today" || route === "progress"
        ? "/me/adaptive-dashboard"
        : route === "coach" ? "/messages" : null;
      const readyResponse = endpoint
        ? page.waitForResponse((response) => response.request().method() === "GET" && response.url().includes(endpoint))
        : null;
      await page.goto(BASE + "/" + route);
      if (readyResponse) assert.equal((await readyResponse).status(), 200, `${route} data response`);
      if (route === "recipes") {
        await page.waitForFunction(() => {
          const area = document.querySelector("#recipeRecommendations");
          return area && !area.querySelector(".skeleton-card") && area.children.length > 0;
        });
        await page.waitForFunction(() => [...document.querySelectorAll(".recipe-art img")].every((img) => img.complete && img.naturalWidth > 0));
      }
      await page.waitForLoadState("networkidle");
    }
    const authDimensions = {};
    for (const route of ["login", "register"]) {
      await page.goto(BASE + "/" + route);
      for (const width of widths) {
        await page.setViewportSize({ width, height: 960 });
        await noOverflow(route + "/" + width);
        authDimensions[route + "/" + width] = await page.evaluate(() => ({
          card: document.querySelector(".auth-card").getBoundingClientRect()
            .width,
          input: document.querySelector(".form-control").getBoundingClientRect()
            .height,
          button: document
            .querySelector(".auth-form>[type=submit]")
            .getBoundingClientRect().height,
        }));
        if (width === 390 || width === 1280)
          await screenshot(route + "-" + width);
      }
      for (const theme of ["light", "dark"]) {
        await page.evaluate((t) => ui.setTheme(t), theme);
        await page.waitForTimeout(300);
        const results = await new AxeBuilder({ page })
          .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
          .analyze();
        audit.push({ route, theme, violations: results.violations });
      }
    }
    for (const width of widths)
      assert.deepEqual(
        authDimensions["login/" + width],
        authDimensions["register/" + width],
      );
    console.log("PASS auth dimensions at representative widths");
    await page.locator("#name").fill("Deniz");
    const email = `review-${Date.now()}@example.com`;
    const password = "UiReview-2026!";
    await page.locator("#email").fill(email);
    await page.locator("#password").fill(password);
    await page.locator("#passwordConfirm").fill(password);
    await page.locator("#registerBtn").click();
    await page.waitForURL("**/onboarding");
    for (const width of widths) {
      await page.setViewportSize({ width, height: 960 });
      await noOverflow("onboarding/" + width);
      if (width === 390 || width === 1280) await screenshot("onboarding-" + width);
    }
    for (const theme of ["light", "dark"]) {
      await page.evaluate((t) => ui.setTheme(t), theme);
      await page.waitForTimeout(300);
      const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
      audit.push({ route: "onboarding", theme, violations: results.violations });
    }
    await page.setViewportSize({ width: 1280, height: 960 });
    await page.locator('input[name="goal_type"][value="lose"]').check();
    await page.locator("#stepNext").click();
    await page.locator("#onBirth").fill("1990-01-01");
    await page.locator("#onSex").selectOption("male");
    await page.locator("#onHeight").fill("180");
    await page.locator("#onWeight").fill("72");
    await page.locator("#onTarget").fill("68");
    await page.locator("#stepNext").click();
    await page.locator('input[name="activity_level"][value="moderate"]').check();
    await page.locator("#stepNext").click();
    await page.locator('input[name="training_frequency"][value="three_four"]').check();
    await page.locator("#stepNext").click();
    await page.locator('input[name="pace_percent_per_week"][value="0.50"]').check();
    await page.locator("#stepFinish").click();
    await page.locator("#onboardingComplete").waitFor({ state: "visible" });
    await page.locator("#onboardingComplete a[href='/today']").click();
    await page.waitForURL("**/today");
    await page.waitForFunction(
      () =>
        document.querySelector("#heroStatusBadge").textContent === "Kayıt Yok",
    );
    assert.equal(await page.locator("#calorieValue").textContent(), "—");
    console.log("PASS register / empty data semantics");
    await page.evaluate(async () => {
      const now = new Date();
      for (const [i, name, cal] of [
        [0, "Avokadolu tost ve yumurta", 420],
        [1, "Izgara tavuk ve bulgur salatası", 610],
      ]) {
        await api.createMeal({
          occurred_at: new Date(now.getTime() - i * 60000).toISOString(),
          meal_type: i ? "lunch" : "breakfast",
          original_description: name,
          items: [
            {
              name,
              quantity: 1,
              unit: "porsiyon",
              calories: cal,
              protein_g: 30,
              carbs_g: 40,
              fat_g: 15,
            },
          ],
        });
      }
      for (let i = 6; i >= 0; i--)
        await api.createWeight({
          occurred_at: new Date(
            now.getTime() - i * 86400000 - 3600000,
          ).toISOString(),
          weight_kg: 72 + i * 0.15,
        });
    });
    await gotoApp("today");
    await page.waitForFunction(
      () => document.querySelector("#calorieValue").textContent === "1.030",
    );
    await page.locator("#btnQuickAddMeal").click();
    await page.locator("#mealDescription").fill("Yoğurt ve ceviz");
    for (const [id, value] of Object.entries({
      itemCalories: "200",
      itemProtein: "15",
      itemCarbs: "20",
      itemFat: "8",
    }))
      await page.locator("#" + id).fill(value);
    const manualMealAdaptiveResponse = page.waitForResponse((response) => response.request().method() === "GET" && response.url().includes("/me/adaptive-dashboard"));
    await page.locator("#btnSubmitAddMeal").click();
    assert.equal((await manualMealAdaptiveResponse).status(), 200);
    await page.waitForFunction(
      () => document.querySelector("#calorieValue").textContent === "1.230",
    );
    console.log("PASS manual meal creation");
    await gotoApp("meals");
    await page.locator(".btn-edit-meal").first().click();
    await page.locator("#photoItemsList .item-cal").fill("250");
    await page.locator("#btnConfirmSavePhotoMeal").click();
    await page.waitForFunction(
      () => document.querySelector("#dayTotalCalories").textContent === "1.280",
    );
    await page.locator(".btn-delete-meal").first().click();
    await page.keyboard.press("Escape");
    await page.locator(".btn-delete-meal").first().click();
    const deletedMealResponse = page.waitForResponse((response) => response.request().method() === "DELETE" && response.url().includes("/me/meals/"));
    await page.locator("#confirmDialogConfirm").click();
    assert.equal((await deletedMealResponse).status(), 204);
    await page.waitForFunction(
      () => document.querySelector("#dayTotalCalories").textContent === "1.030",
    );
    console.log("PASS edit/delete and confirmation cancel");
    await gotoApp("today");
    await page
      .locator("#dashboardPhotoInput")
      .setInputFiles(path.join(output, "register-390.png"));
    await page.locator("#modalPhotoMealReview").waitFor({ state: "visible" });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.waitForTimeout(350);
    await page.screenshot({
      path: path.join(output, "photo-review.png"),
      fullPage: false,
    });
    await noOverflow("photo-review");
    const photoAudit = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
      .analyze();
    audit.push({
      route: "photo-review",
      theme: "dark",
      violations: photoAudit.violations,
    });
    await page.locator("#photoItemsList .item-cal").fill("-1");
    await page.locator("#btnConfirmSavePhotoMeal").click();
    assert(await page.locator("#modalPhotoMealReview").isVisible());
    await page.locator("#photoItemsList .item-cal").fill("300.25");
    const photoAdaptiveResponse = page.waitForResponse((response) => response.request().method() === "GET" && response.url().includes("/me/adaptive-dashboard"));
    await page.locator("#btnConfirmSavePhotoMeal").click();
    assert.equal((await photoAdaptiveResponse).status(), 200);
    await page.waitForFunction(
      () => !document.querySelector("#modalPhotoMealReview").open,
    );
    assert.equal(
      await page.evaluate(async () =>
        Number((await api.getDailyNutrition()).totals.calories),
      ),
      1330.25,
    );
    console.log(
      "PASS photo preview/edit/negative validation/save with decimal values",
    );
    await gotoApp("meals");
    await page.locator("#btnNewCustomFood").click();
    const longFoodName = "Final QA " + "ÇokUzunYiyecekAdı".repeat(8);
    await page.locator("#customFoodName").fill(longFoodName);
    for (const [id, value] of Object.entries({ customFoodCalories: "90", customFoodProtein: "6", customFoodCarbs: "8", customFoodFat: "5" }))
      await page.locator("#" + id).fill(value);
    await page.locator("#formCustomFood button[type=submit]").click();
    await page.locator("#modalFoodLog").waitFor({ state: "visible" });
    await page.locator("#foodLogQuantity").fill("150");
    await page.locator("#foodLogMealType").selectOption("extra");
    await page.waitForFunction(() => document.querySelector("#foodLogPreview").textContent.includes("135 kcal"));
    await page.locator("#formFoodLog button[type=submit]").click();
    await page.waitForFunction(() => document.querySelector("#dayTotalCalories").textContent === "1.465");
    await page.locator("#foodSearchInput").fill("Final QA");
    await page.locator("#foodSearchForm button[type=submit]").click();
    await page.locator(".food-result").waitFor();
    await page.setViewportSize({ width: 390, height: 844 });
    await noOverflow("long food search result");
    const favoritedFoodResponse = page.waitForResponse((response) => response.request().method() === "PUT" && response.url().includes("/favorite"));
    await page.locator(".favorite-food").first().click();
    assert.equal((await favoritedFoodResponse).status(), 204);
    await page.locator(".favorite-food").first().waitFor({ state: "visible" });
    await page.waitForFunction(() => document.querySelector(".favorite-food")?.getAttribute("aria-pressed") === "true");
    await page.locator('[data-food-list="favorites"]').click();
    await page.locator(".food-result").waitFor();
    assert((await page.locator("#foodSearchResults").textContent()).includes(longFoodName));
    await page.locator('[data-food-list="recent"]').click();
    await page.locator(".food-result").waitFor();
    const qaFoodId = await page.evaluate(async () => (await api.searchFoods("Final QA")).local[0].id);
    await page.evaluate(async (foodId) => {
      await api.apiFetch("/me/recipes", { method: "POST", body: {
        name: "Final QA " + "ÇokUzunTarifAdı".repeat(8), description: "Yapılandırılmış ara öğün", servings: 1,
        instructions: ["Yoğurdu kaseye al."], tags: ["ara öğün"],
        ingredients: [{ food_id: foodId, quantity: "150", unit: "g" }],
      }});
      await api.apiFetch("/me/recipes", { method: "POST", body: {
        name: "Final QA kısmi tarif", description: "Malzemesi henüz eşleşmedi", servings: 1,
        instructions: ["Malzemeyi hazırla."], tags: ["ara öğün"],
        ingredients: [{ fallback_text: "Eşleşmemiş malzeme", quantity: "1", unit: "porsiyon" }],
      }});
    }, qaFoodId);
    await gotoApp("recipes");
    await page.locator(".recipe-card").first().waitFor();
    assert.equal(await page.locator(".recipe-card").count(), 2);
    await noOverflow("long recipe name/mobile");
    assert((await page.locator("#recipeRecommendations").textContent()).includes("Kısmi besin değeri"));
    await page.locator(".recipe-open").first().click();
    await page.locator("#recipeDetail").waitFor({ state: "visible" });
    assert((await page.locator("#recipeDetailBody").textContent()).includes("Malzemeler"));
    await noOverflow("recipe detail/mobile");
    console.log("PASS custom/structured Extra, search, Recent, Favorites, recipes and partial nutrition");
    await gotoApp("profile");
    await page.locator("#profPace").selectOption("0.25");
    await page.locator("#btnSaveProfile").click();
    await page.waitForFunction(() =>
      document
        .querySelector("#profileSaveState")
        .textContent.includes("yeniden hesaplandı"),
    );
    assert.equal(await page.locator("#planStatus").textContent(), "Plan hazır");
    console.log("PASS deterministic profile recalculation");
    await gotoApp("progress");
    await page.locator("#btnOpenAddWeight").click();
    await page.locator("#inputProgressWeightKg").fill("71.8");
    await page.locator("#btnSubmitProgressWeight").click();
    await page.waitForFunction(
      () => document.querySelector("#currentWeightVal").textContent === "71,8",
    );
    console.log("PASS weight log");
    await page.locator("#btnAddSteps").click();
    await page.locator("#inputSteps").fill("5000");
    await page.locator("#formSteps button[type=submit]").click();
    await page.waitForFunction(() => document.querySelector("#todaySteps").textContent === "5.000");
    await page.locator("#btnAddWorkout").click();
    await page.locator("#workoutType").selectOption("walking");
    await page.locator("#workoutDuration").fill("30");
    const workoutAdaptiveResponse = page.waitForResponse((response) => response.request().method() === "GET" && response.url().includes("/me/adaptive-dashboard"));
    await page.locator("#formWorkout button[type=submit]").click();
    assert.equal((await workoutAdaptiveResponse).status(), 200);
    await page.waitForFunction(() => document.querySelector("#todayWorkoutMinutes").textContent === "30 dk");
    console.log("PASS steps and workout through UI");
    await gotoApp("coach");
    await page.waitForTimeout(350);
    await page.locator("#chatInput").fill("Bugün nasıl bir denge kurabilirim?");
    await page.locator("#btnSend").click();
    await page.locator(".bubble-assistant .chat-bubble").waitFor();
    assert.equal(await page.locator(".chat-bubble ul li").count(), 3);
    console.log("PASS chat and rich text");
    for (const route of routes) {
      await gotoApp(route);
      for (const theme of ["light", "dark"]) {
        await page.evaluate((t) => ui.setTheme(t), theme);
        await page.waitForTimeout(300);
        for (const width of widths) {
          await page.setViewportSize({ width, height: 900 });
          await noOverflow(route + "/" + theme + "/" + width);
          if (width === 390 || width === 1280)
            await screenshot(route + "-" + theme + "-" + width);
        }
        const results = await new AxeBuilder({ page })
          .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
          .analyze();
        audit.push({ route, theme, violations: results.violations });
      }
    }
    // Long content is wrapped, never clipped or blindly truncated in messages.
    await gotoApp("today");
    await page.evaluate(() => {
      document.querySelector("#greetingTitle").textContent =
        "Merhaba, " + "ÇokUzunBirKullanıcıAdı".repeat(12);
      document.querySelector("#sidebarUserName").textContent =
        "Kullanıcı".repeat(30);
    });
    for (const width of [390, 1280]) {
      await page.setViewportSize({ width, height: 900 });
      await noOverflow("long username/" + width);
    }
    await gotoApp("coach");
    await page.evaluate(() => {
      document.querySelector(".bubble-assistant .chat-bubble").innerHTML =
        ui.richText(
          "UzunYanıt".repeat(1000) + "\n\n- Birinci öneri\n- İkinci öneri",
        );
    });
    await page.setViewportSize({ width: 390, height: 844 });
    await noOverflow("long assistant message");
    // Source labels/URLs are exercised through the actual rendering path.
    await page.route("**/conversations/*/messages", async (route) => {
      if (route.request().method() !== "GET") return route.continue();
      await route.fulfill({
        json: [
          {
            role: "assistant",
            content: "Kaynaklı yanıt",
            created_at: new Date().toISOString(),
            grounding_sources: [
              {
                url: "https://example.com/nutrition",
                title: "Örnek beslenme kaynağı",
              },
              { url: "javascript:alert(1)", title: "Invalid URL" },
            ],
          },
        ],
      });
    });
    await page.reload();
    await page.locator(".grounding-link").waitFor();
    assert.equal(await page.locator(".grounding-link").count(), 1);
    assert(
      (await page.locator(".grounding-badge").textContent()).includes(
        "Google Arama kaynakları",
      ),
    );
    await page.unroute("**/conversations/*/messages");
    await page.emulateMedia({ colorScheme: "dark" });
    await page.evaluate(() => ui.setTheme("system"));
    assert.equal(await page.locator("html").getAttribute("data-theme"), "dark");
    await page.locator("#mobileThemeToggle").click();
    assert.equal(
      await page.locator("html").getAttribute("data-theme"),
      "light",
    );
    const finalChatHistoryResponse = page.waitForResponse((response) => response.request().method() === "GET" && response.url().includes("/messages"));
    await page.reload();
    assert.equal((await finalChatHistoryResponse).status(), 200);
    assert.equal(
      await page.locator("html").getAttribute("data-theme"),
      "light",
    );
    console.log("PASS system/dark/light theme persistence");
    await page.goto(BASE + "/logout");
    await page.waitForURL("**/login");
    await page.locator("#email").fill(email);
    await page.locator("#password").fill(password);
    await page.locator("#loginBtn").click();
    await page.waitForURL("**/today");
    console.log("PASS logout/login");
    const violations = audit
      .filter((entry) => entry.violations.length)
      .map((entry) => ({
        ...entry,
        violations: entry.violations.map((v) => ({
          id: v.id,
          nodes: v.nodes.map((n) => ({
            target: n.target,
            summary: n.failureSummary,
          })),
        })),
      }));
    const expectedNoContentAborts = failedFirstParty.filter((entry) => entry.failure === "net::ERR_ABORTED" && noContentResponses.has(`${entry.method} ${entry.url}`));
    const genuineFailedFirstParty = failedFirstParty.filter((entry) => !expectedNoContentAborts.includes(entry));
    fs.writeFileSync(
      path.join(output, "report.json"),
      JSON.stringify(
        {
          browser: process.env.UI_BROWSER || "chromium",
          checks,
          authDimensions,
          errors,
          consoleErrors,
          failedFirstParty,
          expectedNoContentAborts,
          genuineFailedFirstParty,
          badFirstPartyResponses,
          violations,
        },
        null,
        2,
      ),
    );
    console.log(
      "REPORT",
      JSON.stringify({ checks, errors, consoleErrors, genuineFailedFirstParty, expectedNoContentAborts: expectedNoContentAborts.length, badFirstPartyResponses, violations, output }),
    );
    assert.equal(errors.length, 0, "Browser JavaScript errors");
    assert.equal(genuineFailedFirstParty.length, 0, "Failed first-party requests");
    assert.equal(badFirstPartyResponses.length, 0, "First-party 500/static 404 responses");
    assert.equal(violations.length, 0, "Accessibility violations");
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
