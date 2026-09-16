/**
 * NutriCoach Progress View Logic — Weight tracking, native SVG chart, 7-day adherence
 */
document.addEventListener("DOMContentLoaded", async () => {
  const currentWeightVal = document.getElementById("currentWeightVal");
  const weightTrendPill = document.getElementById("weightTrendPill");
  const goalWeightVal = document.getElementById("goalWeightVal");
  const trendWeightVal = document.getElementById("trendWeightVal");
  const remainingWeightVal = document.getElementById("remainingWeightVal");
  const weightDeltaVal = document.getElementById("weightDeltaVal");
  const chartContainer = document.getElementById("chartContainer");
  const chartPlaceholder = document.getElementById("chartPlaceholder");
  const weightSvgChart = document.getElementById("weightSvgChart");
  const weightLogsList = document.getElementById("weightLogsList");

  const recordedDaysBadge = document.getElementById("recordedDaysBadge");
  const weeklyAvgCalories = document.getElementById("weeklyAvgCalories");
  const weeklyMissingDays = document.getElementById("weeklyMissingDays");

  const btnOpenAddWeight = document.getElementById("btnOpenAddWeight");
  const modalProgressWeight = document.getElementById("modalProgressWeight");
  const formProgressWeight = document.getElementById("formProgressWeight");
  const btnCloseProgressWeight = document.getElementById(
    "btnCloseProgressWeight",
  );
  const btnCancelProgressWeight = document.getElementById(
    "btnCancelProgressWeight",
  );

  let chartWeights = [];
  let chartTrendKg = null;
  setupWeightModal();
  await loadProgressData();

  async function loadProgressData() {
    weightLogsList.innerHTML = '<div class="skeleton-card"></div>';

    try {
      const [currentWt, weights, profile, weekly, activityToday] = await Promise.all([
        api.getCurrentWeight().catch((error) => {
          if (error.status === 404) return null;
          throw error;
        }),
        api.listWeights(50),
        api.getProfile(),
        api.getWeeklyNutrition(),
        api.getTodayActivity(),
      ]);

      renderWeightHero(currentWt, weights, profile);
      renderSvgChart(weights);
      renderWeeklyAdherence(weekly);
      renderWeightLogs(weights);
      renderActivity(activityToday);
      try { renderAdaptiveProgress(await api.getAdaptiveDashboard()); }
      catch (adaptiveError) {
        console.error("Adaptive progress unavailable:", adaptiveError);
        document.getElementById("adaptiveWeightTrend").textContent = "Eğilim şu an yüklenemedi.";
      }
    } catch (err) {
      console.error("Error loading progress data:", err);
      weightLogsList.innerHTML =
        '<div class="empty-state-box">Kayıtlar yüklenemedi. Sayfayı yenileyerek tekrar deneyebilirsin.</div>';
      ui.showToast("İlerleme verileri yüklenirken bir hata oluştu.", "error");
    }
  }

  function renderAdaptiveProgress(data) {
    const trend = data.weight;
    trendWeightVal.textContent = trend.current_trend_weight_kg == null ? "Yeterli ölçüm yok" : `${ui.formatNumber(trend.current_trend_weight_kg, 1)} kg`;
    chartTrendKg = trend.current_trend_weight_kg == null ? null : Number(trend.current_trend_weight_kg);
    renderSvgChart(chartWeights);
    const weightLine = trend.current_trend_weight_kg == null
      ? "Kilo eğilimi için ölçüm gerekli."
      : `Son ölçüm ${ui.formatNumber(trend.current_raw_weight_kg, 1)} kg · Yumuşatılmış eğilim ${ui.formatNumber(trend.current_trend_weight_kg, 1)} kg · ${confidenceLabel(trend.confidence)}`;
    document.getElementById("adaptiveWeightTrend").textContent = weightLine;
    document.getElementById("weightTrendPill").textContent = trend.confidence === "insufficient" ? "Eğilim için erken" : `Eğilim güveni: ${confidenceLabel(trend.confidence)}`;
    document.getElementById("weightDeltaVal").textContent = trend.weekly_change_kg == null ? "Yeterli ölçüm yok" : `${Number(trend.weekly_change_kg) > 0 ? "+" : ""}${ui.formatNumber(trend.weekly_change_kg, 2)} kg`;
    const goal = data.goal;
    const maintenance = goal.planned_rate_percent_per_week != null && Number(goal.planned_rate_percent_per_week) === 0;
    remainingWeightVal.textContent = goal.status === "goal_reached" || maintenance ? "Koruma" : goal.remaining_weight_kg == null ? "Henüz hesaplanmadı" : `${ui.formatNumber(goal.remaining_weight_kg, 1)} kg`;
    const paceText = value => value == null ? "Henüz hesaplanamadı" : `${Number(value) > 0 ? "+" : ""}${ui.formatNumber(value, 2)}% / hafta`;
    const rangeText = (start, end) => start && end ? `${ui.formatDate(start)} – ${ui.formatDate(end)}` : "Henüz güvenilir bir aralık yok";
    document.getElementById("plannedPace").textContent = goal.planned_rate_percent_per_week == null ? "Belirlenmedi" : Number(goal.planned_rate_percent_per_week) === 0 ? "Koruma" : `${ui.formatNumber(goal.planned_rate_percent_per_week, 2)}% / hafta`;
    document.getElementById("actualPace").textContent = paceText(goal.actual_rate_percent_per_week);
    document.getElementById("plannedEta").textContent = maintenance ? "Koruma hedefinde tarih aralığı yok" : rangeText(goal.planned_eta_earliest, goal.planned_eta_latest);
    document.getElementById("trendEta").textContent = rangeText(goal.trend_eta_earliest, goal.trend_eta_latest);
    const expenditure = data.expenditure;
    document.getElementById("adaptiveExpenditure").textContent = expenditure.estimated_expenditure_kcal == null
      ? "Enerji harcaması tahmini için plan veya yeterli veri gerekli."
      : `Enerji harcaması tahmini: ${ui.formatNumber(expenditure.estimated_expenditure_kcal)} kcal/gün · ${expenditure.source === "adaptive_estimate" ? "Kayıtlardan uyarlanan tahmin" : "İlk plan tahmini"} · Güven: ${confidenceLabel(expenditure.confidence)}`;
    const week = data.weekly_review;
    document.getElementById("adaptiveWeekly").textContent = week.nutrition.usable_days < 3 ? "Daha güvenilir bir yorum için birkaç gün daha düzenli kayıt tutabilirsin." : "Kayıtların, beslenme ve hareket örüntülerini birlikte görmene yardımcı olur.";
    document.getElementById("reviewUsableDays").textContent = `${week.nutrition.usable_days} / 7 gün`;
    document.getElementById("reviewCalories").textContent = week.nutrition.average_over_usable_days ? `${ui.formatNumber(week.nutrition.average_over_usable_days.calories)} kcal` : "Yeterli veri yok";
    document.getElementById("reviewProtein").textContent = week.nutrition.usable_days === 0 ? "Yeterli kayıt yok" : week.nutrition.protein_hit_days == null ? "Hedef yok" : `${week.nutrition.protein_hit_days} / ${week.nutrition.usable_days} gün`;
    weeklyAvgCalories.textContent = week.nutrition.average_over_usable_days ? `${ui.formatNumber(week.nutrition.average_over_usable_days.calories)} kcal` : "Yeterli kayıt yok";
    document.getElementById("reviewActivity").textContent = `${week.activity.workout_count} egzersiz · ${week.activity.workout_minutes} dk`;
    document.getElementById("adaptiveTargetSuggestion").textContent = week.target_suggestion.action === "insufficient_data" ? "Hedefi değerlendirmek için henüz yeterli düzenli kayıt yok." : week.target_suggestion.reason;
    const game = data.gamification;
    document.getElementById("loggingStreak").textContent = ui.formatNumber(game.current_logging_streak);
    document.getElementById("consistencyRate").textContent = `${ui.formatNumber(game.logging_consistency_14d_percent)}%`;
    const achievementLabels = { first_complete_day: "İlk kapsamlı kayıt", three_day_logging_streak: "3 günlük seri", seven_day_logging_streak: "7 günlük seri", five_of_seven_usable_days: "Haftalık düzen", protein_consistency: "Protein tutarlılığı", regular_weigh_ins: "Düzenli ölçüm", activity_consistency: "Hareket düzeni" };
    const list = document.getElementById("achievementList"); list.replaceChildren();
    for (const key of game.achievements) { const badge = document.createElement("span"); badge.className = "badge achievement-badge"; badge.textContent = achievementLabels[key] || "Tutarlılık"; list.appendChild(badge); }
    if (!game.achievements.length) list.textContent = "Başarılar, düzenli kayıtlarla görünür.";
  }

  function confidenceLabel(value) { return ({ insufficient: "yetersiz veri", low: "düşük", medium: "orta", high: "yüksek" })[value] || value; }

  document.getElementById("weeklyCoachLink")?.addEventListener("click", (event) => {
    sessionStorage.setItem("nutricoach_coach_draft", event.currentTarget.dataset.coachDraft);
  });

  function renderActivity(data) {
    document.getElementById("todaySteps").textContent = data.total_steps == null ? "Kayıt yok" : ui.formatNumber(data.total_steps);
    document.getElementById("todayWorkoutMinutes").textContent = `${data.total_workout_minutes} dk`;
    document.getElementById("todayActivityCalories").textContent = data.estimated_activity_calories == null ? "Hesaplanmadı" : `${ui.formatNumber(data.estimated_activity_calories)} kcal`;
    const labels = { walking: "Yürüyüş", running: "Koşu", cycling: "Bisiklet", strength: "Kuvvet", swimming: "Yüzme", yoga: "Yoga", other: "Diğer" };
    document.getElementById("todayWorkouts").innerHTML = data.workouts.length ? data.workouts.map(row => `<div class="meal-card"><div class="meal-card-top"><strong>${labels[row.activity_type] || row.activity_type}</strong><span>${row.duration_minutes} dk · ${row.estimated_calories == null ? "Enerji tahmini yok" : ui.formatNumber(row.estimated_calories) + " kcal tahmini"}</span></div></div>`).join("") : '<div class="empty-state-box">Bugün için egzersiz kaydı yok.</div>';
  }

  const stepsDialog = document.getElementById("modalSteps");
  document.getElementById("btnAddSteps")?.addEventListener("click", () => stepsDialog.showModal());
  document.querySelectorAll("[data-close-steps]").forEach(button => button.addEventListener("click", () => stepsDialog.close()));
  document.getElementById("formSteps")?.addEventListener("submit", async event => { event.preventDefault(); try { await api.putDailySteps({ day: ui.localDate(), step_count: Number(document.getElementById("inputSteps").value), source: "manual" }); stepsDialog.close(); await loadProgressData(); ui.showToast("Adım kaydı güncellendi.", "success"); } catch (error) { ui.showToast(error.message, "error"); } });
  const workoutDialog = document.getElementById("modalWorkout");
  document.getElementById("btnAddWorkout")?.addEventListener("click", () => workoutDialog.showModal());
  document.querySelectorAll("[data-close-workout]").forEach(button => button.addEventListener("click", () => workoutDialog.close()));
  document.getElementById("formWorkout")?.addEventListener("submit", async event => { event.preventDefault(); try { await api.createWorkout({ occurred_at: new Date().toISOString(), activity_type: document.getElementById("workoutType").value, duration_minutes: Number(document.getElementById("workoutDuration").value), intensity: document.getElementById("workoutIntensity").value, source: "manual", notes: null }); workoutDialog.close(); await loadProgressData(); ui.showToast("Egzersiz kaydedildi.", "success"); } catch (error) { ui.showToast(error.message, "error"); } });

  function renderWeightHero(currentWt, weights, profile) {
    if (!currentWt) {
      currentWeightVal.textContent = "—";
      weightTrendPill.textContent = "Kayıt Yok";
      weightTrendPill.className = "trend-pill";
      goalWeightVal.textContent = profile?.goal_weight_kg
        ? `${ui.formatNumber(profile.goal_weight_kg, 1)} kg`
        : "Belirlenmedi";
      weightDeltaVal.textContent = "—";
      trendWeightVal.textContent = "Yeterli ölçüm yok";
      remainingWeightVal.textContent = "Yeterli ölçüm yok";
      return;
    }

    const currentKg = Number(currentWt.weight_kg);
    currentWeightVal.textContent = ui.formatNumber(currentKg, 1);

    // Goal Weight
    if (profile?.goal_weight_kg) {
      const goalKg = Number(profile.goal_weight_kg);
      goalWeightVal.textContent = `${ui.formatNumber(goalKg, 1)} kg`;
    } else {
      goalWeightVal.textContent = "Belirlenmedi";
    }

    weightDeltaVal.textContent = "Eğilim yükleniyor";
    weightTrendPill.textContent = "Eğilim yükleniyor";
  }

  let chartResizeFrame = null;
  new ResizeObserver(() => {
    if (chartResizeFrame !== null) return;
    chartResizeFrame = requestAnimationFrame(() => {
      chartResizeFrame = null;
      renderSvgChart(chartWeights);
    });
  }).observe(chartContainer);

  function renderSvgChart(weights) {
    chartWeights = weights;
    const w = Math.max(280, chartContainer.clientWidth);
    weightSvgChart.setAttribute("viewBox", `0 0 ${w} 240`);
    if (!weights || weights.length === 0) {
      chartPlaceholder.style.display = "block";
      weightSvgChart.style.display = "none";
      return;
    }

    chartPlaceholder.style.display = "none";
    weightSvgChart.style.display = "block";

    // Sort ascending by time
    const sorted = [...weights].sort(
      (a, b) => new Date(a.occurred_at) - new Date(b.occurred_at),
    );

    if (sorted.length === 1) {
      chartPlaceholder.textContent = `Tek ölçüm mevcut: ${ui.formatNumber(sorted[0].weight_kg, 1)} kg. Eğilim için birkaç ölçüm daha gerekli.`;
      chartPlaceholder.style.display = "block";
      weightSvgChart.style.display = "none";
      return;
    }

    const values = sorted.map((w) => Number(w.weight_kg));
    if (chartTrendKg != null) values.push(chartTrendKg);
    const minVal = Math.min(...values) - 0.5;
    const maxVal = Math.max(...values) + 0.5;
    const range = maxVal - minVal || 1;

    const h = 200;
    const padX = 48;
    const padY = 30;

    const points = sorted.map((item, idx) => {
      const firstTime = new Date(sorted[0].occurred_at).getTime();
      const span =
        new Date(sorted[sorted.length - 1].occurred_at).getTime() - firstTime;
      const fraction = span
        ? (new Date(item.occurred_at).getTime() - firstTime) / span
        : 0.5;
      const x = padX + fraction * (w - 2 * padX);
      const val = Number(item.weight_kg);
      const y = h - padY - ((val - minVal) / range) * (h - 2 * padY);
      return { x, y, val, date: item.occurred_at };
    });

    const polylinePoints = points.map((p) => `${p.x},${p.y}`).join(" ");

    // SVG Grid & Labels
    let svgHtml = `
            <!-- Guidelines -->
            <line x1="${padX}" y1="${padY}" x2="${w - padX}" y2="${padY}" stroke="var(--border)" stroke-dasharray="4 4" />
            <line x1="${padX}" y1="${h - padY}" x2="${w - padX}" y2="${h - padY}" stroke="var(--border)" stroke-dasharray="4 4" />
            
            <text x="${padX - 8}" y="${padY + 4}" text-anchor="end" font-size="14" fill="var(--text-subtle)">${ui.formatNumber(maxVal, 1)}</text>
            <text x="${padX - 8}" y="${h - padY + 4}" text-anchor="end" font-size="14" fill="var(--text-subtle)">${ui.formatNumber(minVal, 1)}</text>

            <!-- Line Path -->
            <polyline points="${polylinePoints}" fill="none" stroke="var(--accent)" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" />
        `;

    if (chartTrendKg != null) {
      const trendY = h - padY - ((chartTrendKg - minVal) / range) * (h - 2 * padY);
      svgHtml += `<line x1="${padX}" y1="${trendY}" x2="${w - padX}" y2="${trendY}" stroke="var(--color-primary)" stroke-width="2" stroke-dasharray="5 5" opacity=".7"/><text x="${w - padX}" y="${Math.max(14, trendY - 8)}" text-anchor="end" font-size="12" fill="var(--color-primary)">Güncel eğilim</text>`;
    }

    // Points
    points.forEach((p) => {
      const dateFmt = ui.formatDate(ui.localDate(p.date));
      svgHtml += `
                <g class="chart-point-group">
                    <circle cx="${p.x}" cy="${p.y}" r="5" fill="var(--color-surface)" stroke="var(--accent)" stroke-width="1.8" />
                    <title>${dateFmt}: ${ui.formatNumber(p.val, 1)} kg</title>
                </g>
            `;
    });

    svgHtml += `<text x="${padX}" y="218" font-size="14" fill="var(--text-muted)">${shortDate(sorted[0].occurred_at)}</text><text x="${w - padX}" y="218" text-anchor="end" font-size="14" fill="var(--text-muted)">${shortDate(sorted[sorted.length - 1].occurred_at)}</text>`;
    weightSvgChart.innerHTML = svgHtml;
  }

  function shortDate(value) {
    return new Date(ui.localDate(value) + "T12:00:00").toLocaleDateString(
      "tr-TR",
      { day: "numeric", month: "short" },
    );
  }

  function renderWeeklyAdherence(weekly) {
    if (!weekly) return;

    const chart = document.getElementById("weeklyChart");
    const days = weekly.days || [];
    const max = Math.max(
      1,
      ...days.map((day) => Number(day.totals?.calories || 0)),
    );
    chart.replaceChildren();
    for (const day of days) {
      const col = document.createElement("div");
      col.className = "week-column" + (day.has_records ? "" : " is-missing");
      const label = new Date(day.date + "T12:00:00").toLocaleDateString(
        "tr-TR",
        { weekday: "short" },
      );
      col.title = `${ui.formatDate(day.date)}: ${day.has_records ? ui.formatNumber(day.totals.calories) + " kcal" : "Kayıt yok"}`;
      col.setAttribute("aria-label", col.title);
      col.innerHTML =
        '<div class="week-track"><div class="week-bar"></div></div><span></span>';
      col.querySelector("span").textContent = label;
      col.style.setProperty(
        "--bar-height",
        `${day.has_records ? (Number(day.totals.calories) / max) * 100 : 0}%`,
      );
      chart.appendChild(col);
    }
    recordedDaysBadge.textContent = `${weekly.recorded_days} / 7 gün kayıtlı`;
    weeklyMissingDays.textContent = `${weekly.missing_days} gün`;

    // The adaptive review supplies an average only for days with enough data.
  }

  function renderWeightLogs(weights) {
    if (!weights || weights.length === 0) {
      weightLogsList.innerHTML =
        '<div class="card empty-state-box">Henüz kaydedilmiş kilo verisi bulunmuyor.</div>';
      return;
    }

    weightLogsList.innerHTML = weights
      .map((w) => {
        const dateStr = ui.formatDate(ui.localDate(w.occurred_at));
        const timeStr = ui.formatTime(w.occurred_at);
        const kg = ui.formatNumber(w.weight_kg, 2);

        return `
                <div class="meal-card">
                    <div class="meal-card-top">
                        <span class="meal-desc">${kg} kg</span>
                        <div class="row">
                            <span class="meal-time">${dateStr}, ${timeStr}</span>
                            <button class="btn-icon-subtle btn-delete-weight" data-id="${w.id}" aria-label="Kilo kaydını sil">
                                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>
                            </button>
                        </div>
                    </div>
                </div>
            `;
      })
      .join("");

    // Attach Delete Handlers
    document.querySelectorAll(".btn-delete-weight").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const weightId = btn.getAttribute("data-id");
        const confirmed = await ui.confirmDialog(
          "Kilo Kaydını Sil",
          "Bu kilo ölçümünü silmek istediğinize emin misiniz?",
        );
        if (confirmed) {
          try {
            await api.deleteWeight(weightId);
            ui.showToast("Kilo kaydı silindi.", "success");
            await loadProgressData();
          } catch (err) {
            ui.showToast(err.message || "Kilo kaydı silinemedi.", "error");
          }
        }
      });
    });
  }

  function setupWeightModal() {
    if (!btnOpenAddWeight || !modalProgressWeight) return;

    btnOpenAddWeight.addEventListener("click", () => {
      formProgressWeight.reset();
      const now = new Date();
      // Local ISO string for datetime-local input
      const localIso = new Date(now.getTime() - now.getTimezoneOffset() * 60000)
        .toISOString()
        .slice(0, 16);
      const timeInput = document.getElementById("inputProgressWeightTime");
      timeInput.value = localIso;
      timeInput.dataset.defaultLocalValue = localIso;
      timeInput.dataset.defaultOccurredAt = now.toISOString();
      modalProgressWeight.showModal();
    });

    btnCloseProgressWeight?.addEventListener("click", () =>
      modalProgressWeight.close(),
    );
    btnCancelProgressWeight?.addEventListener("click", () =>
      modalProgressWeight.close(),
    );

    formProgressWeight.addEventListener("submit", async (e) => {
      e.preventDefault();
      const weight = parseFloat(
        document.getElementById("inputProgressWeightKg").value,
      );
      const dtVal = document.getElementById("inputProgressWeightTime").value;
      const timeInput = document.getElementById("inputProgressWeightTime");
      const occurredAt = dtVal === timeInput.dataset.defaultLocalValue
        ? timeInput.dataset.defaultOccurredAt
        : new Date(dtVal).toISOString();

      try {
        await api.createWeight({
          occurred_at: occurredAt,
          weight_kg: weight,
        });
        modalProgressWeight.close();
        ui.showToast("Kilo kaydedildi.", "success");
        await loadProgressData();
      } catch (err) {
        ui.showToast(err.message || "Kilo kaydedilemedi.", "error");
      }
    });
  }
});
