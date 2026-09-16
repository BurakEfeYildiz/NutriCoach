document.addEventListener("DOMContentLoaded", async () => {
  const form = document.getElementById("formProfile");
  const dietaryForm = document.getElementById("profileDietaryForm");
  const dietaryInput = document.getElementById("profileDietaryExclusions");
  try { dietaryInput.value = (await api.getDietaryExclusions()).foods.join(", "); }
  catch (error) { ui.showToast(error.message, "error"); }
  dietaryForm.addEventListener("submit", async event => {
    event.preventDefault(); const button = event.submitter; button.disabled = true; button.setAttribute("aria-busy", "true");
    try { await api.putDietaryExclusions(dietaryInput.value.split(",").map(value => value.trim()).filter(Boolean)); ui.showToast("Beslenme tercihleri kaydedildi.", "success"); }
    catch (error) { ui.showToast(error.message, "error"); }
    finally { button.disabled = false; button.removeAttribute("aria-busy"); }
  });
  const state = document.getElementById("profileSaveState");
  const fmt = (value, suffix = "") => value == null ? "—" : `${Number(value).toLocaleString("tr-TR", { maximumFractionDigits: 2 })}${suffix}`;
  const dateFmt = (value) => value ? new Intl.DateTimeFormat("tr-TR", { day: "numeric", month: "short", year: "numeric" }).format(new Date(`${value}T12:00:00`)) : "—";
  function renderPlan(plan) {
    document.getElementById("planCalories").textContent = fmt(plan.daily_calorie_target);
    document.getElementById("planProtein").textContent = fmt(plan.protein_target_g);
    document.getElementById("planCarbs").textContent = fmt(plan.carbohydrate_target_g);
    document.getElementById("planFat").textContent = fmt(plan.fat_target_g);
    document.getElementById("planWeight").textContent = fmt(plan.current_weight_kg, " kg");
    document.getElementById("planExpenditure").textContent = fmt(plan.estimated_expenditure_kcal, " kcal/gün");
    document.getElementById("planRate").textContent = fmt(plan.planned_rate_kg_per_week, " kg/hafta");
    document.getElementById("planEta").textContent = plan.planned_eta_earliest ? `${dateFmt(plan.planned_eta_earliest)} – ${dateFmt(plan.planned_eta_latest)}` : "Uygulanmıyor";
    const labels = { ready: "Plan hazır", constrained: "Güvenlik sınırı uygulandı", goal_reached: "Hedefe ulaşıldı", unsupported_minor: "Otomatik hedef yok", unsupported_pregnancy_breastfeeding: "Otomatik hedef yok" };
    document.getElementById("planStatus").textContent = labels[plan.status] || "Eksik plan";
    const notice = document.getElementById("planNotice");
    if (plan.constraint_reason) { notice.textContent = plan.constraint_reason; notice.className = "auth-alert auth-alert-info"; } else notice.classList.add("hidden");
  }
  try {
    const [profile, plan] = await Promise.all([api.getProfile(), api.getNutritionPlan()]);
    form.profBirthDate.value = profile.birth_date || ""; form.profSex.value = profile.biological_sex || "female"; form.profHeight.value = profile.height_cm || ""; form.profGoal.value = profile.goal_type || "maintain"; form.profGoalWeight.value = profile.goal_weight_kg || ""; form.profActivityLevel.value = profile.activity_level || "sedentary"; form.profTraining.value = profile.training_frequency || "none"; form.profPace.value = String(profile.pace_percent_per_week ?? 0); form.profPregnancy.value = String(Boolean(profile.pregnancy_or_breastfeeding)); renderPlan(plan);
  } catch (error) { state.textContent = error.message; state.className = "auth-alert auth-alert-error"; }
  form.addEventListener("submit", async (event) => {
    event.preventDefault(); const button = document.getElementById("btnSaveProfile"); button.disabled = true;
    try {
      const plan = await api.updateNutritionProfile({ birth_date: form.profBirthDate.value, biological_sex: form.profSex.value, height_cm: form.profHeight.value, target_weight_kg: form.profGoalWeight.value, goal_type: form.profGoal.value, activity_level: form.profActivityLevel.value, training_frequency: form.profTraining.value, pace_percent_per_week: form.profGoal.value === "maintain" ? "0" : form.profPace.value, pregnancy_or_breastfeeding: form.profPregnancy.value === "true" });
      renderPlan(plan); state.textContent = "Planın yeniden hesaplandı ve kaydedildi."; state.className = "form-help"; ui.showToast("Beslenme planın güncellendi.", "success");
    } catch (error) { state.textContent = error.message; state.className = "auth-alert auth-alert-error"; } finally { button.disabled = false; }
  });
  const categories = { food_preference: "Yemek tercihi", food_dislike: "Sevilmeyen yiyecek", dietary_habit: "Beslenme alışkanlığı", practical_constraint: "Pratik kısıt", lifestyle: "Yaşam tarzı", routine: "Rutin", constraint: "Kısıt" };
  async function loadMemories() {
    const list = document.getElementById("memoriesList"), badge = document.getElementById("memoryCountBadge");
    try {
      const memories = await api.listMemories(); badge.textContent = `${memories.length} kayıt`; list.replaceChildren();
      if (!memories.length) { const empty = document.createElement("div"); empty.className = "empty-state-box"; empty.textContent = "Henüz kaydedilmiş bir beslenme tercihi yok."; list.append(empty); return; }
      memories.forEach((memory) => { const card = document.createElement("article"); card.className = "card card-muted memory-item-card"; const content = document.createElement("div"); const label = document.createElement("span"); label.className = "badge"; label.textContent = categories[memory.category] || "Tercih"; const value = document.createElement("p"); value.className = "memory-text"; value.textContent = memory.value; content.append(label, value); const remove = document.createElement("button"); remove.type = "button"; remove.className = "btn btn-ghost btn-sm"; remove.textContent = "Kaldır"; remove.addEventListener("click", async () => { if (await ui.confirmDialog("Hafızadan kaldır", "Bu tercihi koçun hafızasından kaldırmak istiyor musun?")) { await api.deleteMemory(memory.id); ui.showToast("Tercih kaldırıldı.", "success"); await loadMemories(); } }); card.append(content, remove); list.append(card); });
    } catch (error) { list.replaceChildren(); const failed = document.createElement("div"); failed.className = "empty-state-box"; failed.textContent = "Tercihler yüklenemedi."; list.append(failed); }
  }
  await loadMemories();
});
