/**
 * NutriCoach Progress View Logic — Weight tracking, native SVG chart, 7-day adherence
 */
document.addEventListener('DOMContentLoaded', async () => {
    const currentWeightVal = document.getElementById('currentWeightVal');
    const weightTrendPill = document.getElementById('weightTrendPill');
    const goalWeightVal = document.getElementById('goalWeightVal');
    const weightDeltaVal = document.getElementById('weightDeltaVal');
    const chartContainer = document.getElementById('chartContainer');
    const chartPlaceholder = document.getElementById('chartPlaceholder');
    const weightSvgChart = document.getElementById('weightSvgChart');
    const weightLogsList = document.getElementById('weightLogsList');

    const recordedDaysBadge = document.getElementById('recordedDaysBadge');
    const weeklyAvgCalories = document.getElementById('weeklyAvgCalories');
    const weeklyMissingDays = document.getElementById('weeklyMissingDays');

    const btnOpenAddWeight = document.getElementById('btnOpenAddWeight');
    const modalProgressWeight = document.getElementById('modalProgressWeight');
    const formProgressWeight = document.getElementById('formProgressWeight');
    const btnCloseProgressWeight = document.getElementById('btnCloseProgressWeight');
    const btnCancelProgressWeight = document.getElementById('btnCancelProgressWeight');

    await loadProgressData();
    setupWeightModal();

    async function loadProgressData() {
        weightLogsList.innerHTML = '<div class="skeleton-card"></div>';

        try {
            const [currentWt, weights, profile, weekly] = await Promise.all([
                api.getCurrentWeight().catch(() => null),
                api.listWeights(50).catch(() => []),
                api.getProfile().catch(() => null),
                api.getWeeklyNutrition().catch(() => null),
            ]);

            renderWeightHero(currentWt, weights, profile);
            renderSvgChart(weights);
            renderWeeklyAdherence(weekly);
            renderWeightLogs(weights);
        } catch (err) {
            console.error('Error loading progress data:', err);
            ui.showToast('İlerleme verileri yüklenirken bir hata oluştu.', 'error');
        }
    }

    function renderWeightHero(currentWt, weights, profile) {
        if (!currentWt) {
            currentWeightVal.textContent = '—';
            weightTrendPill.textContent = 'Kayıt Yok';
            weightTrendPill.className = 'trend-pill';
            goalWeightVal.textContent = profile?.goal_weight_kg ? `${ui.formatNumber(profile.goal_weight_kg, 1)} kg` : 'Belirlenmedi';
            weightDeltaVal.textContent = '—';
            return;
        }

        const currentKg = Number(currentWt.weight_kg);
        currentWeightVal.textContent = ui.formatNumber(currentKg, 1);

        // Goal Weight
        if (profile?.goal_weight_kg) {
            const goalKg = Number(profile.goal_weight_kg);
            goalWeightVal.textContent = `${ui.formatNumber(goalKg, 1)} kg`;
        } else {
            goalWeightVal.textContent = 'Belirlenmedi';
        }

        // Trend & Delta
        if (weights.length >= 2) {
            const latest = Number(weights[0].weight_kg);
            const earliest = Number(weights[weights.length - 1].weight_kg);
            const delta = latest - earliest;
            const deltaStr = delta > 0 ? `+${ui.formatNumber(delta, 1)} kg` : `${ui.formatNumber(delta, 1)} kg`;
            weightDeltaVal.textContent = deltaStr;

            if (delta < -0.3) {
                weightTrendPill.textContent = 'Düşüşte ↓';
                weightTrendPill.className = 'trend-pill trend-decreasing';
            } else if (delta > 0.3) {
                weightTrendPill.textContent = 'Artışta ↑';
                weightTrendPill.className = 'trend-pill trend-increasing';
            } else {
                weightTrendPill.textContent = 'Dengede ~';
                weightTrendPill.className = 'trend-pill';
            }
        } else {
            weightDeltaVal.textContent = 'İlk ölçüm';
            weightTrendPill.textContent = 'Tek Ölçüm';
            weightTrendPill.className = 'trend-pill';
        }
    }

    function renderSvgChart(weights) {
        if (!weights || weights.length === 0) {
            chartPlaceholder.style.display = 'block';
            weightSvgChart.style.display = 'none';
            return;
        }

        chartPlaceholder.style.display = 'none';
        weightSvgChart.style.display = 'block';

        // Sort ascending by time
        const sorted = [...weights].sort((a, b) => new Date(a.occurred_at) - new Date(b.occurred_at));

        if (sorted.length === 1) {
            // Single measurement display
            const wt = Number(sorted[0].weight_kg);
            weightSvgChart.innerHTML = `
                <text x="300" y="100" text-anchor="middle" fill="var(--text-muted)" font-size="14">Tek ölçüm mevcut: ${ui.formatNumber(wt, 1)} kg</text>
                <circle cx="300" cy="120" r="6" fill="var(--accent)" />
            `;
            return;
        }

        const values = sorted.map(w => Number(w.weight_kg));
        const minVal = Math.min(...values) - 0.5;
        const maxVal = Math.max(...values) + 0.5;
        const range = maxVal - minVal || 1;

        const w = 600;
        const h = 200;
        const padX = 40;
        const padY = 30;

        const points = sorted.map((item, idx) => {
            const x = padX + (idx / (sorted.length - 1)) * (w - 2 * padX);
            const val = Number(item.weight_kg);
            const y = h - padY - ((val - minVal) / range) * (h - 2 * padY);
            return { x, y, val, date: item.occurred_at };
        });

        const polylinePoints = points.map(p => `${p.x},${p.y}`).join(' ');

        // SVG Grid & Labels
        let svgHtml = `
            <!-- Guidelines -->
            <line x1="${padX}" y1="${padY}" x2="${w - padX}" y2="${padY}" stroke="var(--border)" stroke-dasharray="4 4" />
            <line x1="${padX}" y1="${h - padY}" x2="${w - padX}" y2="${h - padY}" stroke="var(--border)" stroke-dasharray="4 4" />
            
            <text x="${padX - 8}" y="${padY + 4}" text-anchor="end" font-size="11" fill="var(--text-subtle)">${ui.formatNumber(maxVal, 1)}</text>
            <text x="${padX - 8}" y="${h - padY + 4}" text-anchor="end" font-size="11" fill="var(--text-subtle)">${ui.formatNumber(minVal, 1)}</text>

            <!-- Line Path -->
            <polyline points="${polylinePoints}" fill="none" stroke="var(--accent)" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" />
        `;

        // Points
        points.forEach(p => {
            const dateFmt = ui.formatDate(p.date.split('T')[0]);
            svgHtml += `
                <g class="chart-point-group">
                    <circle cx="${p.x}" cy="${p.y}" r="5" fill="#ffffff" stroke="var(--accent)" stroke-width="2.5" />
                    <title>${dateFmt}: ${ui.formatNumber(p.val, 1)} kg</title>
                </g>
            `;
        });

        weightSvgChart.innerHTML = svgHtml;
    }

    function renderWeeklyAdherence(weekly) {
        if (!weekly) return;

        recordedDaysBadge.textContent = `${weekly.recorded_days} / 7 gün kayıtlı`;
        weeklyMissingDays.textContent = `${weekly.missing_days} gün`;

        if (weekly.average_over_recorded_days && weekly.recorded_days > 0) {
            const avgCals = ui.formatNumber(weekly.average_over_recorded_days.calories || 0);
            weeklyAvgCalories.textContent = `${avgCals} kcal`;
        } else {
            weeklyAvgCalories.textContent = '—';
        }
    }

    function renderWeightLogs(weights) {
        if (!weights || weights.length === 0) {
            weightLogsList.innerHTML = '<div class="card empty-state-box">Henüz kaydedilmiş kilo verisi bulunmuyor.</div>';
            return;
        }

        weightLogsList.innerHTML = weights.map(w => {
            const dateStr = ui.formatDate(w.occurred_at.split('T')[0]);
            const timeStr = ui.formatTime(w.occurred_at);
            const kg = ui.formatNumber(w.weight_kg, 2);

            return `
                <div class="meal-card" style="margin-bottom: 8px;">
                    <div class="meal-card-top">
                        <span class="meal-desc" style="font-size: 1.1rem; color: var(--accent);">${kg} kg</span>
                        <div style="display: flex; align-items: center; gap: 10px;">
                            <span class="meal-time">${dateStr}, ${timeStr}</span>
                            <button class="btn-icon-subtle btn-delete-weight" data-id="${w.id}" aria-label="Kilo kaydını sil">
                                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>
                            </button>
                        </div>
                    </div>
                </div>
            `;
        }).join('');

        // Attach Delete Handlers
        document.querySelectorAll('.btn-delete-weight').forEach(btn => {
            btn.addEventListener('click', async () => {
                const weightId = btn.getAttribute('data-id');
                const confirmed = await ui.confirmDialog('Kilo Kaydını Sil', 'Bu kilo ölçümünü silmek istediğinize emin misiniz?');
                if (confirmed) {
                    try {
                        await api.deleteWeight(weightId);
                        ui.showToast('Kilo kaydı silindi.', 'success');
                        await loadProgressData();
                    } catch (err) {
                        ui.showToast(err.message || 'Kilo kaydı silinemedi.', 'error');
                    }
                }
            });
        });
    }

    function setupWeightModal() {
        if (!btnOpenAddWeight || !modalProgressWeight) return;

        btnOpenAddWeight.addEventListener('click', () => {
            formProgressWeight.reset();
            const now = new Date();
            // Local ISO string for datetime-local input
            const localIso = new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
            document.getElementById('inputProgressWeightTime').value = localIso;
            modalProgressWeight.showModal();
        });

        btnCloseProgressWeight?.addEventListener('click', () => modalProgressWeight.close());
        btnCancelProgressWeight?.addEventListener('click', () => modalProgressWeight.close());

        formProgressWeight.addEventListener('submit', async (e) => {
            e.preventDefault();
            const weight = parseFloat(document.getElementById('inputProgressWeightKg').value);
            const dtVal = document.getElementById('inputProgressWeightTime').value;
            const occurredAt = new Date(dtVal).toISOString();

            try {
                await api.createWeight({
                    occurred_at: occurredAt,
                    weight_kg: weight,
                });
                modalProgressWeight.close();
                ui.showToast('Kilo kaydedildi.', 'success');
                await loadProgressData();
            } catch (err) {
                ui.showToast(err.message || 'Kilo kaydedilemedi.', 'error');
            }
        });
    }
});
