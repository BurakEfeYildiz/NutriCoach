document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("onboardingForm"), steps = [...form.querySelectorAll(".onboarding-step")], back = document.getElementById("stepBack"), next = document.getElementById("stepNext"), finish = document.getElementById("stepFinish"), alert = document.getElementById("onboardingAlert"); let current = 0;
  function updatePaceEquivalents() { const weight = Number(form.elements.current_weight_kg.value); form.querySelectorAll("[data-pace-kg]").forEach((node) => { const kg = weight * Number(node.dataset.paceKg) / 100; node.textContent = Number.isFinite(kg) && kg > 0 ? `yaklaşık ${kg.toLocaleString("tr-TR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} kg/hafta` : "kilo bilgisi gerekli"; }); }
  function updatePaceMode() { const maintain = form.elements.goal_type.value === "maintain"; form.querySelectorAll("[data-change-pace]").forEach((label) => { label.classList.toggle("hidden", maintain); label.querySelector("input").disabled = maintain; }); const maintenance = form.querySelector("[data-maintain-pace]"); maintenance.classList.toggle("hidden", !maintain); maintenance.querySelector("input").disabled = !maintain; if (maintain) maintenance.querySelector("input").checked = true; }
  function render() { steps.forEach((step, index) => step.classList.toggle("hidden", index !== current)); back.disabled = current === 0; next.classList.toggle("hidden", current === steps.length - 1); finish.classList.toggle("hidden", current !== steps.length - 1); document.getElementById("stepCounter").textContent = `Adım ${current + 1} / ${steps.length}`; const progress = document.querySelector(".onboarding-progress"); progress.setAttribute("aria-valuenow", String(current + 1)); document.getElementById("onboardingProgress").style.width = `${((current + 1) / steps.length) * 100}%`; updatePaceMode(); updatePaceEquivalents(); }
  function validStep() { const inputs = [...steps[current].querySelectorAll("input, select")]; const ok = inputs.every((input) => input.type === "radio" ? form.querySelector(`[name="${input.name}"]:checked`) : input.reportValidity()); if (!ok) { alert.textContent = "Devam etmek için bu adımdaki alanları tamamla."; alert.className = "auth-alert auth-alert-error"; alert.focus(); } else alert.classList.add("hidden"); return ok; }
  next.addEventListener("click", () => { if (validStep()) { current += 1; render(); } }); back.addEventListener("click", () => { current -= 1; render(); });
  form.addEventListener("change", updatePaceMode);
  form.addEventListener("submit", async (event) => {
    event.preventDefault(); if (!validStep()) return;
    finish.disabled = true; finish.setAttribute("aria-busy", "true");
    const data = Object.fromEntries(new FormData(form));
    if (data.goal_type === "maintain") data.pace_percent_per_week = "0";
    data.pregnancy_or_breastfeeding = data.pregnancy_or_breastfeeding === "true";
    try {
      const plan = await api.completeOnboarding(data);
      const fmt = value => value == null ? "—" : ui.formatNumber(value, 1);
      document.getElementById("onCompleteCalories").textContent = plan.daily_calorie_target == null ? "—" : ui.formatNumber(plan.daily_calorie_target);
      document.getElementById("onCompleteProtein").textContent = fmt(plan.protein_target_g);
      document.getElementById("onCompleteCarbs").textContent = fmt(plan.carbohydrate_target_g);
      document.getElementById("onCompleteFat").textContent = fmt(plan.fat_target_g);
      document.getElementById("onCompletePace").textContent = data.goal_type === "maintain" ? "Hedef: mevcut kiloyu koruma." : plan.planned_rate_percent_per_week == null ? "Planlanan hız uygulanmıyor." : `Planlanan hız: ${fmt(plan.planned_rate_percent_per_week)}% vücut ağırlığı / hafta`;
      document.getElementById("onCompleteEta").textContent = data.goal_type === "maintain" ? "Koruma hedefinde bitiş tarihi belirlenmez." : plan.planned_eta_earliest && plan.planned_eta_latest ? `Planlanan hedef aralığı: ${ui.formatDate(plan.planned_eta_earliest)} – ${ui.formatDate(plan.planned_eta_latest)}. Bu bir garanti değildir.` : "Hedef tarihi için yeterli plan verisi yok.";
      if (plan.daily_calorie_target == null) document.getElementById("onboardingCompleteNotice").textContent = "Bu durumda otomatik kalori hedefi oluşturulmaz; bilgilerin kaydedildi.";
      form.classList.add("hidden");
      document.getElementById("onboardingComplete").classList.remove("hidden");
      document.getElementById("onboardingComplete").focus();
    } catch (error) {
      alert.textContent = error.message; alert.className = "auth-alert auth-alert-error"; alert.focus();
      finish.disabled = false; finish.removeAttribute("aria-busy");
    }
  }); render();
});
