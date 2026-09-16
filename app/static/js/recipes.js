document.addEventListener("DOMContentLoaded", async () => {
  const list = document.getElementById("recipeRecommendations");
  const detail = document.getElementById("recipeDetail");
  const detailBody = document.getElementById("recipeDetailBody");
  const exclusions = document.getElementById("dietaryExclusions");
  const filterButtons = [...document.querySelectorAll("[data-recipe-filter]")];
  let mealType = "";
  const recommendationReasons = new Map();

  function category(recipe) {
    if (recipe.tags.some(tag => /ara öğün|kahvaltı/.test(tag))) return "snack";
    return /tavuk/i.test(recipe.name) ? "protein" : "meal";
  }

  function recipeArt(recipe) {
    const art = document.createElement("div"); art.className = `recipe-art recipe-art-${category(recipe)}`;
    const image = document.createElement("img"); image.src = "/static/assets/recipe-plate.svg"; image.alt = "";
    art.appendChild(image); return art;
  }

  function nutritionLabel(recipe) {
    if (!recipe.per_serving) return "Besin değeri kısmi; doğrulanmış toplam yok";
    const totals = recipe.per_serving;
    return `${ui.formatNumber(totals.calories)} kcal · Protein ${ui.formatNumber(totals.protein_g)} g · Karbonhidrat ${ui.formatNumber(totals.carbs_g)} g · Yağ ${ui.formatNumber(totals.fat_g)} g / porsiyon`;
  }

  function renderRecipeList(recipes) {
    list.replaceChildren(); recommendationReasons.clear();
    if (!recipes.length) {
      const empty = document.createElement("div");
      empty.className = "card empty-state-box";
      empty.textContent = "Bu tercihlere uygun kayıtlı tarif bulunamadı. Hariç tuttuklarını gözden geçirebilirsin.";
      list.appendChild(empty);
      return;
    }
    recipes.forEach(recipe => {
      recommendationReasons.set(recipe.id, recipe.why_it_fits);
      const card = document.createElement("article");
      card.className = "card recipe-card card-interactive";
      const art = recipeArt(recipe);
      const badge = document.createElement("span"); badge.className = "badge recipe-nutrition-badge"; badge.textContent = recipe.nutrition_status === "partial" ? "Kısmi besin değeri" : "Malzemelerden hesaplandı";
      const title = document.createElement("h3"); title.textContent = recipe.name;
      const summary = document.createElement("p"); summary.textContent = recipe.description;
      const nutrition = document.createElement("p"); nutrition.className = "recipe-energy"; nutrition.textContent = recipe.per_serving ? `${ui.formatNumber(recipe.per_serving.calories)} kcal / porsiyon` : "Doğrulanmış toplam yok";
      const macros = document.createElement("p"); macros.className = "recipe-macros"; macros.textContent = recipe.per_serving ? `Protein ${ui.formatNumber(recipe.per_serving.protein_g)} g · Karbonhidrat ${ui.formatNumber(recipe.per_serving.carbs_g)} g · Yağ ${ui.formatNumber(recipe.per_serving.fat_g)} g` : "Malzeme eşleştirmesi tamamlanmadı";
      const fit = document.createElement("p"); fit.className = "recipe-fit"; fit.textContent = ui.localizeDecimalText(recipe.why_it_fits || "Bugünkü kalan hedef için yeterli kayıt yok.");
      const button = document.createElement("button"); button.className = "btn btn-secondary recipe-open"; button.type = "button"; button.textContent = "Tarifi incele";
      button.addEventListener("click", async () => {
        button.disabled = true; button.setAttribute("aria-busy", "true");
        try { renderDetail(await api.getRecipe(recipe.id), recommendationReasons.get(recipe.id)); detail.scrollIntoView({ behavior: "smooth", block: "start" }); }
        catch (error) { ui.showToast(error.message, "error"); }
        finally { button.disabled = false; button.removeAttribute("aria-busy"); }
      });
      card.append(art, badge, title, summary, nutrition, macros, fit, button);
      list.appendChild(card);
    });
  }

  function renderDetail(recipe, fitReason) {
    document.getElementById("recipeDetailTitle").textContent = recipe.name;
    detailBody.replaceChildren();
    const overview = document.createElement("div"); overview.className = "recipe-detail-overview";
    const info = document.createElement("div"); info.className = "recipe-detail-info";
    const badge = document.createElement("span"); badge.className = "badge"; badge.textContent = recipe.nutrition_status === "partial" ? "Kısmi besin değeri" : "Malzemelerden hesaplandı";
    const servings = document.createElement("p"); servings.className = "muted"; servings.textContent = `${recipe.servings} porsiyonluk tarif`;
    const nutrition = document.createElement("p"); nutrition.className = "recipe-energy"; nutrition.textContent = nutritionLabel(recipe);
    const fit = document.createElement("p"); fit.className = "recipe-fit"; fit.textContent = ui.localizeDecimalText(fitReason || "Kalan hedefe göre porsiyonunu seçebilirsin.");
    info.append(badge, servings, nutrition, fit); overview.append(recipeArt(recipe), info);
    const columns = document.createElement("div"); columns.className = "recipe-detail-columns";
    const ingredientSection = document.createElement("section");
    const ingredientsTitle = document.createElement("h3"); ingredientsTitle.textContent = "Malzemeler";
    const ingredients = document.createElement("ul");
    recipe.ingredients.forEach(item => { const row = document.createElement("li"); row.textContent = `${ui.formatNumber(item.quantity)} ${item.unit} ${item.name}${item.calories == null ? " · besin değeri çözümlenmedi" : ""}`; ingredients.appendChild(row); });
    const instructionsTitle = document.createElement("h3"); instructionsTitle.textContent = "Hazırlanışı";
    const instructions = document.createElement("ol");
    recipe.instructions.forEach(text => { const row = document.createElement("li"); row.textContent = text; instructions.appendChild(row); });
    ingredientSection.append(ingredientsTitle, ingredients);
    const instructionSection = document.createElement("section"); instructionSection.append(instructionsTitle, instructions);
    columns.append(ingredientSection, instructionSection); detailBody.append(overview, columns);
    detail.hidden = false;
  }

  async function loadRecipes() {
    list.innerHTML = '<div class="skeleton-card"></div><div class="skeleton-card"></div>';
    try { renderRecipeList(await api.getRecommendedRecipes(mealType || null)); }
    catch (error) { list.textContent = "Tarif önerileri şu an yüklenemedi."; ui.showToast(error.message, "error"); }
  }

  filterButtons.forEach(button => button.addEventListener("click", async () => {
    mealType = button.dataset.recipeFilter;
    filterButtons.forEach(item => { const selected = item === button; item.classList.toggle("active", selected); item.setAttribute("aria-pressed", String(selected)); });
    detail.hidden = true; await loadRecipes();
  }));
  document.getElementById("closeRecipeDetail").addEventListener("click", () => { detail.hidden = true; });

  try { exclusions.value = (await api.getDietaryExclusions()).foods.join(", "); }
  catch (error) { ui.showToast(error.message, "error"); }
  document.getElementById("dietaryExclusionsForm").addEventListener("submit", async event => {
    event.preventDefault();
    const button = event.submitter; button.disabled = true; button.setAttribute("aria-busy", "true");
    try {
      const foods = exclusions.value.split(",").map(value => value.trim()).filter(Boolean);
      await api.putDietaryExclusions(foods);
      detail.hidden = true;
      await loadRecipes();
      ui.showToast("Tercihler kaydedildi.", "success");
    } catch (error) { ui.showToast(error.message, "error"); }
    finally { button.disabled = false; button.removeAttribute("aria-busy"); }
  });
  await loadRecipes();
});
