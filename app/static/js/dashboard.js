/**
 * NutriCoach Dashboard (Bugün) Logic
 */
document.addEventListener("DOMContentLoaded", async () => {
  let currentUser = null;
  setupQuickActions();

  try {
    currentUser = await api.getMe();
  } catch (e) {
    console.error("Failed to get current user:", e);
  }

  // Set greeting name
  const greetingTitle = document.getElementById("greetingTitle");
  if (greetingTitle && currentUser?.name) {
    greetingTitle.textContent = `Merhaba, ${currentUser.name}`;
  }

  // Load and render
  await loadTodayData();

  async function loadTodayData() {
    try {
      const [daily, meals, profile] = await Promise.all([
        api.getDailyNutrition(),
        api.getTodayMeals(),
        api.getProfile(),
      ]);

      // Set formatted date
      const dateStr = daily?.date || ui.localDate();
      const dateLabel = ui.formatDate(dateStr);
      const greetingDate = document.getElementById("greetingDate");
      const mobileHeaderDate = document.getElementById("mobileHeaderDate");
      if (greetingDate) greetingDate.textContent = dateLabel;
      if (mobileHeaderDate) mobileHeaderDate.textContent = dateLabel;

      renderNutritionHero(daily, profile);
      renderMacros(daily, profile);
      renderTodayMeals(meals);
      try {
        renderAdaptive(await api.getAdaptiveDashboard());
      } catch (adaptiveError) {
        console.error("Adaptive summary unavailable:", adaptiveError);
        document.getElementById("dailyInsights").textContent = "İçgörüler şu an yüklenemedi.";
      }
    } catch (err) {
      console.error("Error loading today data:", err);
      document.getElementById("heroStatusBadge").textContent = "Yüklenemedi";
      document.getElementById("heroSubtext").textContent =
        "Bağlantını kontrol edip sayfayı yenile.";
      document.getElementById("todayMealsList").innerHTML =
        '<div class="empty-state-box">Öğünler yüklenemedi. Sayfayı yenileyerek tekrar deneyebilirsin.</div>';
      ui.showToast("Günün verileri yüklenirken bir hata oluştu.", "error");
    }
  }

  function renderAdaptive(data) {
    const qualityLabels = { none: "Bugün için kayıt yok", partial: "Bugünkü kayıtların kısmi olabilir", likely_complete: "Bugünkü kayıtların kapsamlı görünüyor" };
    document.getElementById("loggingQuality").textContent = qualityLabels[data.today_quality.status];
    document.getElementById("loggingConsistency").textContent = `Son 14 günde anlamlı kayıt tutma oranı: ${ui.formatNumber(data.gamification.logging_consistency_14d_percent)}%`;
    document.getElementById("dashboardActivity").textContent = data.activity.steps_today == null
      ? "Bugün adım kaydı yok; hareketini İlerleme sayfasına ekleyebilirsin."
      : `Bugün ${ui.formatNumber(data.activity.steps_today)} adım kaydettin. Son 7 günün kayıtlı gün ortalaması: ${data.activity.days_7.average_steps_over_recorded_days == null ? "henüz yok" : ui.formatNumber(data.activity.days_7.average_steps_over_recorded_days) + " adım"}.`;
    const container = document.getElementById("dailyInsights");
    container.replaceChildren();
    if (!data.insights.length) {
      const message = document.createElement("p");
      message.className = "muted";
      message.textContent = "İçgörü için daha fazla düzenli kayıt gerekli.";
      container.appendChild(message);
      return;
    }
    for (const insight of data.insights.slice(0, 3)) {
      const row = document.createElement("p");
      row.className = "adaptive-insight";
      row.textContent = ui.localizeDecimalText(insight.text);
      container.appendChild(row);
    }
  }

  function renderNutritionHero(daily, profile) {
    const calValEl = document.getElementById("calorieValue");
    const badgeEl = document.getElementById("heroStatusBadge");
    const targetEl = document.getElementById("calorieTargetVal");
    const remainingEl = document.getElementById("calorieRemainingVal");
    const barEl = document.getElementById("calorieProgressBar");
    const subtextEl = document.getElementById("heroSubtext");
    const ring = document.getElementById("calorieRingFill");
    ring.style.strokeDashoffset = "100";
    ring.style.visibility = daily?.has_records ? "visible" : "hidden";
    remainingEl.style.color = "";

    if (!daily || !daily.has_records) {
      calValEl.textContent = "—";
      badgeEl.textContent = "Kayıt Yok";
      badgeEl.style.background = "var(--surface-secondary)";
      badgeEl.style.color = "var(--text-muted)";
      targetEl.textContent = profile?.calorie_target
        ? `${ui.formatNumber(profile.calorie_target)} kcal`
        : "Belirlenmedi";
      remainingEl.textContent = "—";
      barEl.style.width = "0%";
      subtextEl.textContent = "Henüz bugün için bir öğün kaydetmedin.";
      return;
    }

    const consumed = Number(daily.totals?.calories || 0);
    calValEl.textContent = ui.formatNumber(consumed);
    badgeEl.textContent = "Aktif";
    badgeEl.style.background = "var(--accent-soft)";
    badgeEl.style.color = "var(--accent-text)";

    const target = profile?.calorie_target
      ? Number(profile.calorie_target)
      : null;
    if (target) {
      targetEl.textContent = `${ui.formatNumber(target)} kcal`;
      const remaining =
        daily.remaining_by_target?.calories !== undefined
          ? Number(daily.remaining_by_target.calories)
          : target - consumed;

      if (remaining >= 0) {
        remainingEl.textContent = `${ui.formatNumber(remaining)} kcal`;
        subtextEl.textContent = profile?.plan_status === "goal_reached" ? "Hedefine ulaştın; bugün düzenini gözlemlemeye devam et." : `Günlük hedefe göre ${ui.formatNumber(remaining)} kcal kaldı.`;
      } else {
        remainingEl.textContent = `+${ui.formatNumber(Math.abs(remaining))} kcal aşıldı`;
        remainingEl.style.color = "var(--warning)";
        subtextEl.textContent = "Bugünkü kalori hedefini aştın.";
      }

      const pct = Math.min(
        100,
        Math.max(0, Math.round((consumed / target) * 100)),
      );
      barEl.style.width = `${pct}%`;
      ring.style.strokeDashoffset = String(100 - pct);
      if (consumed > target) barEl.style.background = "var(--warning)";
      else barEl.style.background = "var(--accent)";
    } else {
      targetEl.textContent = "Belirlenmedi";
      remainingEl.textContent = "—";
      barEl.style.width = "100%";
      subtextEl.textContent = "Beslenme planında henüz kalori hedefi yok.";
    }
  }

  function renderMacros(daily, profile) {
    const hasRecords = daily && daily.has_records;
    const totals = daily?.totals || {};

    // Protein
    renderSingleMacro(
      "proteinRatio",
      "proteinFill",
      "proteinRemaining",
      totals.protein_g,
      profile?.protein_target_g,
      daily?.remaining_by_target?.protein_g,
      hasRecords,
    );

    // Carbs
    renderSingleMacro(
      "carbsRatio",
      "carbsFill",
      "carbsRemaining",
      totals.carbs_g,
      profile?.carb_target_g,
      daily?.remaining_by_target?.carbs_g,
      hasRecords,
    );

    // Fat
    renderSingleMacro(
      "fatRatio",
      "fatFill",
      "fatRemaining",
      totals.fat_g,
      profile?.fat_target_g,
      daily?.remaining_by_target?.fat_g,
      hasRecords,
    );
  }

  function renderSingleMacro(
    ratioId,
    fillId,
    remId,
    consumed,
    target,
    remaining,
    hasRecords,
  ) {
    const ratioEl = document.getElementById(ratioId);
    const fillEl = document.getElementById(fillId);
    const remEl = document.getElementById(remId);

    if (!hasRecords) {
      ratioEl.textContent = target ? `— / ${ui.formatNumber(target)} g` : "—";
      fillEl.style.width = "0%";
      remEl.textContent = "Henüz kayıt yok";
      return;
    }

    const consVal = hasRecords ? Number(consumed || 0) : 0;
    const tgtVal = target ? Number(target) : null;

    if (tgtVal) {
      ratioEl.textContent = `${ui.formatNumber(consVal, 1)} / ${ui.formatNumber(tgtVal, 0)} g`;
      const pct = Math.min(100, Math.round((consVal / tgtVal) * 100));
      fillEl.style.width = `${pct}%`;

      const remVal =
        remaining !== undefined && remaining !== null
          ? Number(remaining)
          : tgtVal - consVal;
      if (remVal >= 0) {
        remEl.textContent = `${ui.formatNumber(remVal, 1)} g kaldı`;
      } else {
        remEl.textContent = `${ui.formatNumber(Math.abs(remVal), 1)} g aşıldı`;
      }
    } else {
      ratioEl.textContent = hasRecords
        ? `${ui.formatNumber(consVal, 1)} g`
        : "—";
      fillEl.style.width = hasRecords ? "100%" : "0%";
      remEl.textContent = "Hedef yok";
    }
  }

  function renderTodayMeals(meals) {
    const container = document.getElementById("todayMealsList");
    if (!container) return;

    if (!meals || meals.length === 0) {
      container.innerHTML = `
                <div class="card empty-state-box">
                    <p>Bugün henüz bir öğün kaydetmedin.</p>
                    <p>Yiyecek ekle ile arama yapabilir veya fotoğrafla analiz edebilirsin.</p>
                </div>
            `;
      return;
    }

    container.innerHTML = meals
      .map((meal) => {
        const timeStr = ui.formatTime(meal.occurred_at);
        const typeLabel = ui.translateMealType(meal.meal_type);
        const cals = ui.formatNumber(meal.totals?.calories || 0);
        const p = ui.formatNumber(meal.totals?.protein_g || 0, 1);
        const c = ui.formatNumber(meal.totals?.carbs_g || 0, 1);
        const f = ui.formatNumber(meal.totals?.fat_g || 0, 1);

        const itemsHtml = (meal.items || [])
          .map(
            (item) =>
              `<li>${ui.escapeHtml(item.name)} (${ui.formatNumber(item.quantity, 1)} ${ui.escapeHtml(item.unit)})</li>`,
          )
          .join("");

        return `
                <div class="meal-card" id="meal-${meal.id}">
                    <div class="meal-card-top">
                        <span class="meal-type-tag">${typeLabel}</span>
                        <span class="meal-time">${timeStr}</span>
                    </div>
                    <div class="meal-desc">${ui.escapeHtml(meal.original_description)}</div>
                    ${itemsHtml ? `<ul class="meal-items-list">${itemsHtml}</ul>` : ""}
                    <div class="meal-nutrition-footer">
                        <span class="meal-cals">${cals} kcal</span>
                        <span class="meal-macros-compact">${p}g P · ${c}g K · ${f}g Y</span>
                    </div>
                </div>
            `;
      })
      .join("");
  }

  function setupQuickActions() {
    // Quick Add Meal Modal
    const btnAddMeal = document.getElementById("btnQuickAddMeal");
    const modalAddMeal = document.getElementById("modalAddMeal");
    const formAddMeal = document.getElementById("formAddMeal");
    const btnCloseAddMeal = document.getElementById("btnCloseAddMeal");
    const btnCancelAddMeal = document.getElementById("btnCancelAddMeal");

    if (btnAddMeal && modalAddMeal) {
      btnAddMeal.addEventListener("click", () => modalAddMeal.showModal());
      btnCloseAddMeal?.addEventListener("click", () => modalAddMeal.close());
      btnCancelAddMeal?.addEventListener("click", () => modalAddMeal.close());

      formAddMeal?.addEventListener("submit", async (e) => {
        e.preventDefault();
        const type = document.getElementById("mealType").value;
        const desc = document.getElementById("mealDescription").value;
        const qty = parseFloat(document.getElementById("itemQuantity").value);
        const unit = document.getElementById("itemUnit").value;
        const cal = parseFloat(document.getElementById("itemCalories").value);
        const p = parseFloat(document.getElementById("itemProtein").value);
        const c = parseFloat(document.getElementById("itemCarbs").value);
        const f = parseFloat(document.getElementById("itemFat").value);

        const payload = {
          occurred_at: new Date().toISOString(),
          meal_type: type,
          original_description: desc,
          nutrition_source: "manual",
          items: [
            {
              name: desc,
              quantity: qty,
              unit: unit,
              calories: cal,
              protein_g: p,
              carbs_g: c,
              fat_g: f,
              source: "manual",
            },
          ],
        };

        try {
          await api.createMeal(payload);
          modalAddMeal.close();
          formAddMeal.reset();
          ui.showToast("Öğün başarıyla kaydedildi.", "success");
          await loadTodayData();
        } catch (err) {
          ui.showToast(err.message || "Öğün kaydedilemedi.", "error");
        }
      });
    }

    // Quick Add Meal from Photo
    const btnPhotoMeal = document.getElementById("btnQuickPhotoMeal");
    const photoInput = document.getElementById("dashboardPhotoInput");

    if (btnPhotoMeal && photoInput) {
      btnPhotoMeal.addEventListener("click", () => photoInput.click());

      photoInput.addEventListener("change", async (e) => {
        const file = e.target.files?.[0];
        if (!file) return;
        photoInput.value = "";

        if (file.size > 10 * 1024 * 1024) {
          ui.showToast("Fotoğraf boyutu 10MB'dan küçük olmalıdır.", "error");
          return;
        }

        btnPhotoMeal.disabled = true;

        try {
          const analysis = await ui.analyzePhoto(file);
          btnPhotoMeal.disabled = false;
          ui.openPhotoReviewModal(analysis, file, async () => {
            await loadTodayData();
          });
        } catch (err) {
          btnPhotoMeal.disabled = false;
          ui.showToast(err.message || "Fotoğraf analizi başarısız.", "error");
        }
      });
    }

    // Quick Add Weight Modal
    const btnAddWeight = document.getElementById("btnQuickAddWeight");
    const modalAddWeight = document.getElementById("modalAddWeight");
    const formAddWeight = document.getElementById("formAddWeight");
    const btnCloseAddWeight = document.getElementById("btnCloseAddWeight");
    const btnCancelAddWeight = document.getElementById("btnCancelAddWeight");

    if (btnAddWeight && modalAddWeight) {
      btnAddWeight.addEventListener("click", () => modalAddWeight.showModal());
      btnCloseAddWeight?.addEventListener("click", () =>
        modalAddWeight.close(),
      );
      btnCancelAddWeight?.addEventListener("click", () =>
        modalAddWeight.close(),
      );

      formAddWeight?.addEventListener("submit", async (e) => {
        e.preventDefault();
        const weight = parseFloat(document.getElementById("weightKg").value);

        try {
          await api.createWeight({
            occurred_at: new Date().toISOString(),
            weight_kg: weight,
          });
          modalAddWeight.close();
          formAddWeight.reset();
          ui.showToast("Kilo başarıyla kaydedildi.", "success");
          await loadTodayData();
        } catch (err) {
          ui.showToast(err.message || "Kilo kaydedilemedi.", "error");
        }
      });
    }
  }
});
