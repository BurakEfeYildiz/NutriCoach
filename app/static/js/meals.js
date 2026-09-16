/**
 * NutriCoach Meals View Logic — Date navigation, meal lists, CRUD
 */
document.addEventListener("DOMContentLoaded", async () => {
  let selectedDate = ui.localDate();

  const datePicker = document.getElementById("selectedDateInput");
  const dateDisplayLabel = document.getElementById("dateDisplayLabel");
  const btnPrevDay = document.getElementById("btnPrevDay");
  const btnNextDay = document.getElementById("btnNextDay");
  const btnJumpToday = document.getElementById("btnJumpToday");

  const dayMealCountBadge = document.getElementById("dayMealCountBadge");
  const dayTotalCalories = document.getElementById("dayTotalCalories");
  const dayTotalProtein = document.getElementById("dayTotalProtein");
  const dayTotalCarbs = document.getElementById("dayTotalCarbs");
  const dayTotalFat = document.getElementById("dayTotalFat");
  const mealsList = document.getElementById("mealsList");

  const btnAddNewMeal = document.getElementById("btnAddNewMeal");
  const modalMealForm = document.getElementById("modalMealForm");
  const formMeal = document.getElementById("formMeal");
  const btnCloseMealForm = document.getElementById("btnCloseMealForm");
  const btnCancelMealForm = document.getElementById("btnCancelMealForm");

  // Initialize
  datePicker.value = selectedDate;
  updateDateDisplay();

  // Date Navigation Events
  datePicker.addEventListener("change", async (e) => {
    if (e.target.value) {
      selectedDate = e.target.value;
      updateDateDisplay();
      await loadMealsForDate();
    }
  });

  btnPrevDay.addEventListener("click", async () => {
    changeDate(-1);
  });

  btnNextDay.addEventListener("click", async () => {
    changeDate(1);
  });

  btnJumpToday.addEventListener("click", async () => {
    selectedDate = ui.localDate();
    datePicker.value = selectedDate;
    updateDateDisplay();
    await loadMealsForDate();
  });

  function changeDate(deltaDays) {
    const parts = selectedDate.split("-");
    const d = new Date(parts[0], parts[1] - 1, parts[2]);
    d.setDate(d.getDate() + deltaDays);
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    selectedDate = `${y}-${m}-${day}`;
    datePicker.value = selectedDate;
    updateDateDisplay();
    loadMealsForDate();
  }

  function updateDateDisplay() {
    const isToday = selectedDate === ui.localDate();
    const formatted = ui.formatDate(selectedDate);
    dateDisplayLabel.textContent = isToday ? `Bugün (${formatted})` : formatted;
  }

  async function loadMealsForDate() {
    mealsList.innerHTML = '<div class="skeleton-card"></div>';

    try {
      const [daily, meals] = await Promise.all([
        api.getDailyNutrition(selectedDate),
        api.listMeals(selectedDate),
      ]);

      // Render Day Totals
      if (daily && daily.has_records) {
        dayMealCountBadge.textContent = `${daily.meal_count} öğün`;
        dayTotalCalories.textContent = ui.formatNumber(
          daily.totals?.calories || 0,
        );
        dayTotalProtein.textContent = ui.formatNumber(
          daily.totals?.protein_g || 0,
          1,
        );
        dayTotalCarbs.textContent = ui.formatNumber(
          daily.totals?.carbs_g || 0,
          1,
        );
        dayTotalFat.textContent = ui.formatNumber(daily.totals?.fat_g || 0, 1);
      } else {
        dayMealCountBadge.textContent = "0 öğün";
        dayTotalCalories.textContent = "—";
        dayTotalProtein.textContent = "—";
        dayTotalCarbs.textContent = "—";
        dayTotalFat.textContent = "—";
      }

      // Render Meals List
      if (!meals || meals.length === 0) {
        mealsList.innerHTML = `
                    <div class="card empty-state-box">
                        <p>Bu tarih için henüz kayıtlı öğün bulunmuyor.</p>
                        <p>Yukarıdaki "Öğün Ekle" butonu ile yeni bir öğün kaydedebilirsiniz.</p>
                    </div>
                `;
        return;
      }

      mealsList.innerHTML = meals
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
                `<li>${ui.escapeHtml(item.name)} — ${ui.formatNumber(item.quantity, 1)} ${ui.escapeHtml(item.unit)} (${ui.formatNumber(item.calories)} kcal)</li>`,
            )
            .join("");

          return `
                    <div class="meal-card" id="meal-${meal.id}">
                        <div class="meal-card-top">
                            <span class="meal-type-tag">${typeLabel}</span>
                            <div class="meal-actions">
                                <span class="meal-time">${timeStr}</span><button type="button" class="btn btn-ghost btn-sm btn-edit-meal" data-id="${meal.id}" aria-label="Öğünü düzenle">Düzenle</button>
                                <button class="btn-icon-subtle btn-delete-meal" data-id="${meal.id}" aria-label="Öğünü Sil">
                                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>
                                </button>
                            </div>
                        </div>
                        <div class="meal-desc">${ui.escapeHtml(meal.original_description)}</div>
                        ${itemsHtml ? `<ul class="meal-items-list">${itemsHtml}</ul>` : ""}
                        <div class="meal-nutrition-footer">
                            <span class="meal-cals">${cals} kcal</span>
                            <span class="meal-macros-compact">${p}g Protein · ${c}g Karbonhidrat · ${f}g Yağ</span>
                        </div>
                    </div>
                `;
        })
        .join("");

      document.querySelectorAll(".btn-edit-meal").forEach((button) =>
        button.addEventListener("click", () => {
          const meal = meals.find((item) => item.id === button.dataset.id);
          ui.openPhotoReviewModal(meal, null, loadMealsForDate, meal);
        }),
      );

      // Attach Delete Handlers
      document.querySelectorAll(".btn-delete-meal").forEach((btn) => {
        btn.addEventListener("click", async () => {
          const mealId = btn.getAttribute("data-id");
          const confirmed = await ui.confirmDialog(
            "Öğünü Sil",
            "Bu öğünü silmek istediğinize emin misiniz?",
          );
          if (confirmed) {
            try {
              await api.deleteMeal(mealId);
              ui.showToast("Öğün silindi.", "success");
              await loadMealsForDate();
            } catch (err) {
              ui.showToast(err.message || "Öğün silinemedi.", "error");
            }
          }
        });
      });
    } catch (err) {
      console.error("Error loading meals:", err);
      mealsList.innerHTML =
        '<div class="card empty-state-box">Öğünler yüklenirken bir hata oluştu.</div>';
    }
  }

  // Add Meal Modal Handling
  if (btnAddNewMeal && modalMealForm) {
    btnAddNewMeal.addEventListener("click", () => {
      formMeal.reset();
      const now = new Date();
      const hours = String(now.getHours()).padStart(2, "0");
      const mins = String(now.getMinutes()).padStart(2, "0");
      document.getElementById("inputMealTime").value = `${hours}:${mins}`;
      modalMealForm.showModal();
    });

    btnCloseMealForm?.addEventListener("click", () => modalMealForm.close());
    btnCancelMealForm?.addEventListener("click", () => modalMealForm.close());

    formMeal.addEventListener("submit", async (e) => {
      e.preventDefault();
      const type = document.getElementById("inputMealType").value;
      const timeVal = document.getElementById("inputMealTime").value;
      const desc = document.getElementById("inputMealDescription").value;

      const itemName = document.getElementById("inputItemName").value;
      const qty = parseFloat(
        document.getElementById("inputItemQuantity").value,
      );
      const unit = document.getElementById("inputItemUnit").value;
      const cal = parseFloat(
        document.getElementById("inputItemCalories").value,
      );
      const p = parseFloat(document.getElementById("inputItemProtein").value);
      const c = parseFloat(document.getElementById("inputItemCarbs").value);
      const f = parseFloat(document.getElementById("inputItemFat").value);

      // Construct ISO timestamp from selectedDate + timeVal
      const occurredAt = new Date(
        `${selectedDate}T${timeVal || "12:00"}:00`,
      ).toISOString();

      const payload = {
        occurred_at: occurredAt,
        meal_type: type,
        original_description: desc,
        nutrition_source: "manual",
        items: [
          {
            name: itemName,
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
        modalMealForm.close();
        ui.showToast("Öğün kaydedildi.", "success");
        await loadMealsForDate();
      } catch (err) {
        ui.showToast(err.message || "Öğün kaydedilemedi.", "error");
      }
    });
  }

  const foodResults = document.getElementById("foodSearchResults");
  const foodSearchForm = document.getElementById("foodSearchForm");
  const foodLogDialog = document.getElementById("modalFoodLog");
  const foodLogForm = document.getElementById("formFoodLog");
  let selectedFood = null;
  let preferredMealType = null;

  function sourceLabel(source) {
    return { usda: "USDA verisi", open_food_facts: "Topluluk etiketi", user: "Kendi yiyeceğin" }[source] || "Besin kaydı";
  }

  function renderFoods(foods, external = false, append = false, favorites = false) {
    if (!append) foodResults.replaceChildren();
    if (!foods.length) {
      if (!append) foodResults.innerHTML = '<div class="empty-state-box">Eşleşen yiyecek bulunamadı. Kendi yiyeceğini oluşturabilir veya AI’a anlatabilirsin.</div>';
      return;
    }
    const section = document.createElement("div");
    section.className = "food-results";
    section.innerHTML = `<h3 class="form-section-label">${external ? "Paketli ürünler" : favorites ? "Favorilerin" : "Yiyecek kataloğu"}</h3>` + foods.map((food, index) => `<div class="food-result"><div class="food-result-main"><strong>${ui.escapeHtml(food.canonical_name)}</strong><span class="food-source">${ui.escapeHtml(food.brand || "Genel yiyecek")} · ${sourceLabel(food.source)} · ${ui.formatCompactNumber(food.calories)} kcal / ${food.basis_type === "per_serving" ? "servis" : food.basis_type === "per_100ml" ? "100 ml" : "100 g"}${external && !food.has_complete_nutrition ? " · temel makrolar eksik" : ""}</span><span class="food-macros">${[food.protein_g, food.carbs_g, food.fat_g].some(value => value == null) ? "Makrolar kısmi" : `${ui.formatCompactNumber(food.protein_g)} g protein · ${ui.formatCompactNumber(food.carbs_g)} g karbonhidrat · ${ui.formatCompactNumber(food.fat_g)} g yağ`}</span></div><div class="row">${external || favorites ? "" : `<button class="btn btn-ghost btn-icon favorite-food" data-index="${index}" aria-label="Favorilere ekle" aria-pressed="false"><svg viewBox="0 0 24 24" aria-hidden="true"><use href="/static/assets/icons-v2.svg#star"></use></svg></button>`}<button class="btn btn-primary btn-sm choose-food" data-index="${index}" ${external && !food.has_complete_nutrition ? "disabled" : ""}>${external ? "Doğrula ve seç" : "Seç"}</button></div></div>`).join("");
    foodResults.appendChild(section);
    section.querySelectorAll(".choose-food").forEach((button) => button.addEventListener("click", async () => {
      try {
        selectedFood = foods[Number(button.dataset.index)];
        if (external) selectedFood = await api.cacheExternalFood(selectedFood.source_food_id);
        openFoodLog(selectedFood);
      } catch (error) { ui.showToast(error.message, "error"); }
    }));
    section.querySelectorAll(".favorite-food").forEach(button => button.addEventListener("click", async () => { button.disabled = true; try { await api.favoriteFood(foods[Number(button.dataset.index)].id); button.classList.add("is-favorite"); button.setAttribute("aria-pressed", "true"); button.setAttribute("aria-label", "Favorilerde"); ui.showToast("Favorilere eklendi.", "success"); } catch (error) { ui.showToast(error.message, "error"); } finally { button.disabled = false; } }));
  }

  function openFoodLog(food) {
    document.getElementById("foodLogTitle").textContent = food.canonical_name;
    const measure = document.getElementById("foodLogMeasure");
    const baseUnit = food.basis_type === "per_100ml" ? "ml" : food.basis_type === "per_serving" ? "serving" : "g";
    measure.innerHTML = `<option value="unit:${baseUnit}">${baseUnit === "serving" ? "servis" : baseUnit}</option>` + (food.portions || []).map(p => `<option value="portion:${p.id}">${ui.escapeHtml(p.label)}</option>`).join("");
    document.getElementById("foodLogQuantity").value = baseUnit === "serving" ? 1 : 100;
    if (preferredMealType) document.getElementById("foodLogMealType").value = preferredMealType;
    foodLogDialog.showModal();
    refreshFoodPreview();
  }

  async function refreshFoodPreview() {
    if (!selectedFood) return;
    const quantity = Number(document.getElementById("foodLogQuantity").value);
    const [kind, value] = document.getElementById("foodLogMeasure").value.split(":");
    if (!(quantity > 0)) return;
    try {
      const preview = await api.previewFood({ food_id: selectedFood.id, quantity, portion_id: kind === "portion" ? value : null, unit: kind === "unit" ? value : null });
      document.getElementById("foodLogPreview").textContent = `${ui.formatNumber(preview.calories)} kcal · ${ui.formatNumber(preview.protein_g, 1)} g protein · ${ui.formatNumber(preview.carbs_g, 1)} g karbonhidrat · ${ui.formatNumber(preview.fat_g, 1)} g yağ`;
    } catch (error) { document.getElementById("foodLogPreview").textContent = error.message; }
  }

  foodSearchForm?.addEventListener("submit", async (event) => {
    event.preventDefault(); foodResults.innerHTML = '<div class="skeleton-card"></div>';
    try {
      const result = await api.searchFoods(document.getElementById("foodSearchInput").value, document.getElementById("includeExternalFood").checked);
      renderFoods(result.local);
      if (result.external.length) renderFoods(result.external, true, result.local.length > 0);
    } catch (error) { foodResults.innerHTML = `<div class="empty-state-box">${ui.escapeHtml(error.message)}</div>`; }
  });
  document.querySelectorAll("[data-food-query]").forEach(button => button.addEventListener("click", () => { document.getElementById("foodSearchInput").value = button.dataset.foodQuery; foodSearchForm.requestSubmit(); }));
  document.querySelectorAll("[data-food-list]").forEach(button => button.addEventListener("click", async () => { const favorites = button.dataset.foodList === "favorites"; const foods = favorites ? await api.favoriteFoods() : await api.recentFoods(); renderFoods(foods, false, false, favorites); }));
  document.querySelectorAll("[data-close-food-log]").forEach(button => button.addEventListener("click", () => foodLogDialog.close()));
  document.getElementById("foodLogQuantity")?.addEventListener("input", refreshFoodPreview);
  document.getElementById("foodLogMeasure")?.addEventListener("change", refreshFoodPreview);
  foodLogForm?.addEventListener("submit", async event => {
    event.preventDefault(); const [kind, value] = document.getElementById("foodLogMeasure").value.split(":");
    const now = new Date(); const localTime = `${String(now.getHours()).padStart(2,"0")}:${String(now.getMinutes()).padStart(2,"0")}:00`;
    try { await api.logFood({ food_id: selectedFood.id, quantity: Number(document.getElementById("foodLogQuantity").value), portion_id: kind === "portion" ? value : null, unit: kind === "unit" ? value : null, meal_type: document.getElementById("foodLogMealType").value, occurred_at: new Date(`${selectedDate}T${localTime}`).toISOString() }); foodLogDialog.close(); preferredMealType = null; ui.showToast("Yiyecek günlüğe eklendi.", "success"); await loadMealsForDate(); }
    catch (error) { ui.showToast(error.message, "error"); }
  });

  const customDialog = document.getElementById("modalCustomFood");
  document.getElementById("btnNewCustomFood")?.addEventListener("click", () => customDialog.showModal());
  document.querySelectorAll("[data-close-custom]").forEach(button => button.addEventListener("click", () => customDialog.close()));
  document.getElementById("formCustomFood")?.addEventListener("submit", async event => {
    event.preventDefault();
    try { const food = await api.createCustomFood({ canonical_name: document.getElementById("customFoodName").value, basis_type: "per_100g", basis_amount: 100, basis_unit: "g", calories: Number(document.getElementById("customFoodCalories").value), protein_g: Number(document.getElementById("customFoodProtein").value), carbs_g: Number(document.getElementById("customFoodCarbs").value), fat_g: Number(document.getElementById("customFoodFat").value), aliases: [], portions: [] }); customDialog.close(); selectedFood = food; openFoodLog(food); }
    catch (error) { ui.showToast(error.message, "error"); }
  });

  const photoInput = document.getElementById("foodPhotoInput");
  document.getElementById("btnQuickExtra")?.addEventListener("click", () => { preferredMealType = "extra"; document.getElementById("foodSearchInput").focus(); document.getElementById("foodSearchInput").scrollIntoView({ behavior: "smooth", block: "center" }); });
  const photoButton = document.getElementById("btnFoodPhoto");
  photoButton?.addEventListener("click", () => photoInput.click());
  photoInput?.addEventListener("change", async () => { const file = photoInput.files?.[0]; if (!file) return; photoButton.disabled = true; photoButton.setAttribute("aria-busy", "true"); try { const analysis = await ui.analyzePhoto(file); ui.openPhotoReviewModal(analysis, file, loadMealsForDate); } catch (error) { ui.showToast(error.message, "error"); } finally { photoInput.value = ""; photoButton.disabled = false; photoButton.removeAttribute("aria-busy"); } });
  await loadMealsForDate();
});
