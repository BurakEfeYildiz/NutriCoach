/**
 * NutriCoach Meals View Logic — Date navigation, meal lists, CRUD
 */
document.addEventListener('DOMContentLoaded', async () => {
    let selectedDate = new Date().toISOString().split('T')[0];

    const datePicker = document.getElementById('selectedDateInput');
    const dateDisplayLabel = document.getElementById('dateDisplayLabel');
    const btnPrevDay = document.getElementById('btnPrevDay');
    const btnNextDay = document.getElementById('btnNextDay');
    const btnJumpToday = document.getElementById('btnJumpToday');

    const dayMealCountBadge = document.getElementById('dayMealCountBadge');
    const dayTotalCalories = document.getElementById('dayTotalCalories');
    const dayTotalProtein = document.getElementById('dayTotalProtein');
    const dayTotalCarbs = document.getElementById('dayTotalCarbs');
    const dayTotalFat = document.getElementById('dayTotalFat');
    const mealsList = document.getElementById('mealsList');

    const btnAddNewMeal = document.getElementById('btnAddNewMeal');
    const modalMealForm = document.getElementById('modalMealForm');
    const formMeal = document.getElementById('formMeal');
    const btnCloseMealForm = document.getElementById('btnCloseMealForm');
    const btnCancelMealForm = document.getElementById('btnCancelMealForm');

    // Initialize
    datePicker.value = selectedDate;
    updateDateDisplay();
    await loadMealsForDate();

    // Date Navigation Events
    datePicker.addEventListener('change', async (e) => {
        if (e.target.value) {
            selectedDate = e.target.value;
            updateDateDisplay();
            await loadMealsForDate();
        }
    });

    btnPrevDay.addEventListener('click', async () => {
        changeDate(-1);
    });

    btnNextDay.addEventListener('click', async () => {
        changeDate(1);
    });

    btnJumpToday.addEventListener('click', async () => {
        selectedDate = new Date().toISOString().split('T')[0];
        datePicker.value = selectedDate;
        updateDateDisplay();
        await loadMealsForDate();
    });

    function changeDate(deltaDays) {
        const parts = selectedDate.split('-');
        const d = new Date(parts[0], parts[1] - 1, parts[2]);
        d.setDate(d.getDate() + deltaDays);
        const y = d.getFullYear();
        const m = String(d.getMonth() + 1).padStart(2, '0');
        const day = String(d.getDate()).padStart(2, '0');
        selectedDate = `${y}-${m}-${day}`;
        datePicker.value = selectedDate;
        updateDateDisplay();
        loadMealsForDate();
    }

    function updateDateDisplay() {
        const isToday = selectedDate === new Date().toISOString().split('T')[0];
        const formatted = ui.formatDate(selectedDate);
        dateDisplayLabel.textContent = isToday ? `Bugün (${formatted})` : formatted;
    }

    async function loadMealsForDate() {
        mealsList.innerHTML = '<div class="skeleton-card"></div>';

        try {
            const [daily, meals] = await Promise.all([
                api.getDailyNutrition(selectedDate).catch(() => null),
                api.listMeals(selectedDate).catch(() => []),
            ]);

            // Render Day Totals
            if (daily && daily.has_records) {
                dayMealCountBadge.textContent = `${daily.meal_count} öğün`;
                dayTotalCalories.textContent = ui.formatNumber(daily.totals?.calories || 0);
                dayTotalProtein.textContent = ui.formatNumber(daily.totals?.protein_g || 0, 1);
                dayTotalCarbs.textContent = ui.formatNumber(daily.totals?.carbs_g || 0, 1);
                dayTotalFat.textContent = ui.formatNumber(daily.totals?.fat_g || 0, 1);
            } else {
                dayMealCountBadge.textContent = '0 öğün';
                dayTotalCalories.textContent = '—';
                dayTotalProtein.textContent = '—';
                dayTotalCarbs.textContent = '—';
                dayTotalFat.textContent = '—';
            }

            // Render Meals List
            if (!meals || meals.length === 0) {
                mealsList.innerHTML = `
                    <div class="card empty-state-box">
                        <p>Bu tarih için henüz kayıtlı öğün bulunmuyor.</p>
                        <p style="font-size: 0.8rem; margin-top: 6px;">Yukarıdaki "Öğün Ekle" butonu ile yeni bir öğün kaydedebilirsiniz.</p>
                    </div>
                `;
                return;
            }

            mealsList.innerHTML = meals.map(meal => {
                const timeStr = ui.formatTime(meal.occurred_at);
                const typeLabel = ui.translateMealType(meal.meal_type);
                const cals = ui.formatNumber(meal.totals?.calories || 0);
                const p = ui.formatNumber(meal.totals?.protein_g || 0, 1);
                const c = ui.formatNumber(meal.totals?.carbs_g || 0, 1);
                const f = ui.formatNumber(meal.totals?.fat_g || 0, 1);

                const itemsHtml = (meal.items || []).map(item => 
                    `<li>${item.name} — ${ui.formatNumber(item.quantity, 1)} ${item.unit} (${ui.formatNumber(item.calories)} kcal)</li>`
                ).join('');

                return `
                    <div class="meal-card" id="meal-${meal.id}">
                        <div class="meal-card-top">
                            <span class="meal-type-tag">${typeLabel}</span>
                            <div style="display: flex; align-items: center; gap: 8px;">
                                <span class="meal-time">${timeStr}</span>
                                <button class="btn-icon-subtle btn-delete-meal" data-id="${meal.id}" aria-label="Öğünü Sil">
                                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>
                                </button>
                            </div>
                        </div>
                        <div class="meal-desc">${meal.original_description}</div>
                        ${itemsHtml ? `<ul class="meal-items-list">${itemsHtml}</ul>` : ''}
                        <div class="meal-nutrition-footer">
                            <span class="meal-cals">${cals} kcal</span>
                            <span class="meal-macros-compact">${p}g Protein · ${c}g Karb · ${f}g Yağ</span>
                        </div>
                    </div>
                `;
            }).join('');

            // Attach Delete Handlers
            document.querySelectorAll('.btn-delete-meal').forEach(btn => {
                btn.addEventListener('click', async () => {
                    const mealId = btn.getAttribute('data-id');
                    const confirmed = await ui.confirmDialog('Öğünü Sil', 'Bu öğünü silmek istediğinize emin misiniz?');
                    if (confirmed) {
                        try {
                            await api.deleteMeal(mealId);
                            ui.showToast('Öğün silindi.', 'success');
                            await loadMealsForDate();
                        } catch (err) {
                            ui.showToast(err.message || 'Öğün silinemedi.', 'error');
                        }
                    }
                });
            });

        } catch (err) {
            console.error('Error loading meals:', err);
            mealsList.innerHTML = '<div class="card empty-state-box">Öğünler yüklenirken bir hata oluştu.</div>';
        }
    }

    // Add Meal Modal Handling
    if (btnAddNewMeal && modalMealForm) {
        btnAddNewMeal.addEventListener('click', () => {
            formMeal.reset();
            const now = new Date();
            const hours = String(now.getHours()).padStart(2, '0');
            const mins = String(now.getMinutes()).padStart(2, '0');
            document.getElementById('inputMealTime').value = `${hours}:${mins}`;
            modalMealForm.showModal();
        });

        btnCloseMealForm?.addEventListener('click', () => modalMealForm.close());
        btnCancelMealForm?.addEventListener('click', () => modalMealForm.close());

        formMeal.addEventListener('submit', async (e) => {
            e.preventDefault();
            const type = document.getElementById('inputMealType').value;
            const timeVal = document.getElementById('inputMealTime').value;
            const desc = document.getElementById('inputMealDescription').value;

            const itemName = document.getElementById('inputItemName').value;
            const qty = parseFloat(document.getElementById('inputItemQuantity').value);
            const unit = document.getElementById('inputItemUnit').value;
            const cal = parseFloat(document.getElementById('inputItemCalories').value);
            const p = parseFloat(document.getElementById('inputItemProtein').value);
            const c = parseFloat(document.getElementById('inputItemCarbs').value);
            const f = parseFloat(document.getElementById('inputItemFat').value);

            // Construct ISO timestamp from selectedDate + timeVal
            const occurredAt = new Date(`${selectedDate}T${timeVal || '12:00'}:00`).toISOString();

            const payload = {
                occurred_at: occurredAt,
                meal_type: type,
                original_description: desc,
                nutrition_source: 'manual',
                items: [
                    {
                        name: itemName,
                        quantity: qty,
                        unit: unit,
                        calories: cal,
                        protein_g: p,
                        carbs_g: c,
                        fat_g: f,
                        source: 'manual',
                    }
                ]
            };

            try {
                await api.createMeal(payload);
                modalMealForm.close();
                ui.showToast('Öğün kaydedildi.', 'success');
                await loadMealsForDate();
            } catch (err) {
                ui.showToast(err.message || 'Öğün kaydedilemedi.', 'error');
            }
        });
    }
});
