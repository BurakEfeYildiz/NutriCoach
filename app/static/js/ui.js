/**
 * NutriCoach UI Utilities — Toasts, Dialogs, and Presentation Formatting
 */
const ui = (() => {
    function showToast(message, type = 'success', durationMs = 3500) {
        const container = document.getElementById('toastContainer');
        if (!container) return;

        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        
        const iconSvg = type === 'success' 
            ? `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"></polyline></svg>`
            : `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>`;

        toast.innerHTML = `${iconSvg}<span>${message}</span>`;
        container.appendChild(toast);

        setTimeout(() => {
            toast.style.opacity = '0';
            toast.style.transform = 'translateY(-10px)';
            toast.style.transition = 'all 0.25s ease';
            setTimeout(() => toast.remove(), 250);
        }, durationMs);
    }

    function confirmDialog(title, message) {
        return new Promise((resolve) => {
            const dialog = document.getElementById('confirmDialog');
            const titleEl = document.getElementById('confirmDialogTitle');
            const msgEl = document.getElementById('confirmDialogMessage');
            const cancelBtn = document.getElementById('confirmDialogCancel');
            const confirmBtn = document.getElementById('confirmDialogConfirm');

            if (!dialog) {
                resolve(window.confirm(`${title}\n\n${message}`));
                return;
            }

            titleEl.textContent = title;
            msgEl.textContent = message;

            function cleanup() {
                cancelBtn.removeEventListener('click', onCancel);
                confirmBtn.removeEventListener('click', onConfirm);
                dialog.close();
            }

            function onCancel() {
                cleanup();
                resolve(false);
            }

            function onConfirm() {
                cleanup();
                resolve(true);
            }

            cancelBtn.addEventListener('click', onCancel);
            confirmBtn.addEventListener('click', onConfirm);

            dialog.showModal();
        });
    }

    function formatNumber(value, decimals = 0) {
        if (value === null || value === undefined || isNaN(value)) return '—';
        const num = Number(value);
        return num.toLocaleString('tr-TR', {
            minimumFractionDigits: decimals,
            maximumFractionDigits: decimals,
        });
    }

    function formatDate(dateStr) {
        if (!dateStr) return '';
        // Date format: YYYY-MM-DD
        const parts = dateStr.split('-');
        if (parts.length === 3) {
            const date = new Date(parts[0], parts[1] - 1, parts[2]);
            return date.toLocaleDateString('tr-TR', {
                day: 'numeric',
                month: 'long',
                weekday: 'long',
            });
        }
        return dateStr;
    }

    function formatTime(isoStr) {
        if (!isoStr) return '';
        try {
            const date = new Date(isoStr);
            return date.toLocaleTimeString('tr-TR', {
                hour: '2-digit',
                minute: '2-digit',
            });
        } catch (e) {
            return '';
        }
    }

    function translateMealType(type) {
        const map = {
            breakfast: 'Kahvaltı',
            lunch: 'Öğle Yemeği',
            dinner: 'Akşam Yemeği',
            snack: 'Ara Öğün',
            other: 'Öğün',
        };
        return map[type] || 'Öğün';
    }

    function openPhotoReviewModal(analysis, imageFile, onSaveCallback) {
        const dialog = document.getElementById('modalPhotoMealReview');
        if (!dialog) return;

        const imgPreviewContainer = document.getElementById('photoPreviewContainer');
        const imgPreview = document.getElementById('photoPreviewImg');
        const mealTypeSelect = document.getElementById('photoMealType');
        const mealDescInput = document.getElementById('photoMealDescription');
        const confidenceEl = document.getElementById('photoMealConfidence');
        const itemsList = document.getElementById('photoItemsList');
        const btnAdd = document.getElementById('btnAddPhotoItem');
        const btnClose = document.getElementById('btnClosePhotoMeal');
        const btnCancel = document.getElementById('btnCancelPhotoMeal');
        const btnSave = document.getElementById('btnConfirmSavePhotoMeal');

        let objectUrl = null;
        if (imageFile) {
            objectUrl = URL.createObjectURL(imageFile);
            imgPreview.src = objectUrl;
            imgPreviewContainer.style.display = 'block';
        } else {
            imgPreviewContainer.style.display = 'none';
        }

        mealTypeSelect.value = analysis.meal_type || 'lunch';
        mealDescInput.value = analysis.description || '';
        if (analysis.confidence) {
            confidenceEl.textContent = `Güven: ${analysis.confidence.toUpperCase()}`;
        } else {
            confidenceEl.textContent = 'Yapay Zeka Analizi';
        }

        let items = (analysis.items || []).map(item => ({
            name: item.name || '',
            quantity: item.quantity ?? 1,
            unit: item.unit || 'porsiyon',
            calories: item.calories ?? 0,
            protein_g: item.protein_g ?? 0,
            carbs_g: item.carbs_g ?? 0,
            fat_g: item.fat_g ?? 0,
        }));

        function updateTotals() {
            let totalCal = 0;
            let totalP = 0;
            let totalC = 0;
            let totalF = 0;
            items.forEach(it => {
                totalCal += parseFloat(it.calories) || 0;
                totalP += parseFloat(it.protein_g) || 0;
                totalC += parseFloat(it.carbs_g) || 0;
                totalF += parseFloat(it.fat_g) || 0;
            });
            const calEl = document.getElementById('photoTotalCalories');
            const pEl = document.getElementById('photoTotalProtein');
            const cEl = document.getElementById('photoTotalCarbs');
            const fEl = document.getElementById('photoTotalFat');
            if (calEl) calEl.textContent = `${Math.round(totalCal)} kcal`;
            if (pEl) pEl.textContent = `${Math.round(totalP)}`;
            if (cEl) cEl.textContent = `${Math.round(totalC)}`;
            if (fEl) fEl.textContent = `${Math.round(totalF)}`;
        }

        function renderItems() {
            itemsList.innerHTML = '';
            if (items.length === 0) {
                itemsList.innerHTML = '<p class="empty-hint">Henüz yiyecek eklenmedi.</p>';
                updateTotals();
                return;
            }

            items.forEach((item, index) => {
                const card = document.createElement('div');
                card.className = 'photo-item-card';
                card.innerHTML = `
                    <div class="photo-item-main-row">
                        <input type="text" class="form-control item-name" placeholder="Yiyecek adı" value="${item.name}">
                        <button type="button" class="btn-remove-item" title="Kaldır">&times;</button>
                    </div>
                    <div class="photo-item-fields-grid">
                        <div class="field-col">
                            <label>Miktar</label>
                            <input type="number" class="form-control item-qty" value="${item.quantity}" step="0.1" min="0.01">
                        </div>
                        <div class="field-col">
                            <label>Birim</label>
                            <input type="text" class="form-control item-unit" value="${item.unit}">
                        </div>
                        <div class="field-col">
                            <label>Kalori (kcal)</label>
                            <input type="number" class="form-control item-cal" value="${item.calories}" min="0" step="1">
                        </div>
                        <div class="field-col">
                            <label>Protein (g)</label>
                            <input type="number" class="form-control item-p" value="${item.protein_g}" min="0" step="0.1">
                        </div>
                        <div class="field-col">
                            <label>Karb (g)</label>
                            <input type="number" class="form-control item-c" value="${item.carbs_g}" min="0" step="0.1">
                        </div>
                        <div class="field-col">
                            <label>Yağ (g)</label>
                            <input type="number" class="form-control item-f" value="${item.fat_g}" min="0" step="0.1">
                        </div>
                    </div>
                `;

                const nameInput = card.querySelector('.item-name');
                const qtyInput = card.querySelector('.item-qty');
                const unitInput = card.querySelector('.item-unit');
                const calInput = card.querySelector('.item-cal');
                const pInput = card.querySelector('.item-p');
                const cInput = card.querySelector('.item-c');
                const fInput = card.querySelector('.item-f');
                const btnRemove = card.querySelector('.btn-remove-item');

                nameInput.addEventListener('input', () => { item.name = nameInput.value; });
                qtyInput.addEventListener('input', () => { item.quantity = parseFloat(qtyInput.value) || 0; });
                unitInput.addEventListener('input', () => { item.unit = unitInput.value; });
                calInput.addEventListener('input', () => {
                    item.calories = parseFloat(calInput.value) || 0;
                    updateTotals();
                });
                pInput.addEventListener('input', () => {
                    item.protein_g = parseFloat(pInput.value) || 0;
                    updateTotals();
                });
                cInput.addEventListener('input', () => {
                    item.carbs_g = parseFloat(cInput.value) || 0;
                    updateTotals();
                });
                fInput.addEventListener('input', () => {
                    item.fat_g = parseFloat(fInput.value) || 0;
                    updateTotals();
                });
                btnRemove.addEventListener('click', () => {
                    items.splice(index, 1);
                    renderItems();
                });

                itemsList.appendChild(card);
            });

            updateTotals();
        }

        renderItems();

        function cleanup() {
            if (objectUrl) {
                URL.revokeObjectURL(objectUrl);
                objectUrl = null;
            }
            btnAdd.onclick = null;
            btnClose.onclick = null;
            btnCancel.onclick = null;
            btnSave.onclick = null;
            btnSave.disabled = false;
            btnSave.innerHTML = `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"></polyline></svg> <span>Öğün Olarak Kaydet</span>`;
            dialog.close();
        }

        btnAdd.onclick = () => {
            items.push({
                name: '',
                quantity: 1,
                unit: 'porsiyon',
                calories: 0,
                protein_g: 0,
                carbs_g: 0,
                fat_g: 0,
            });
            renderItems();
        };

        btnClose.onclick = cleanup;
        btnCancel.onclick = cleanup;

        btnSave.onclick = async () => {
            if (items.length === 0) {
                showToast('Lütfen en az bir yiyecek ekleyin.', 'error');
                return;
            }
            const desc = mealDescInput.value.trim() || 'Öğün';
            const payload = {
                meal_type: mealTypeSelect.value,
                description: desc,
                items: items.map(it => ({
                    name: it.name.trim() || 'Yiyecek',
                    quantity: parseFloat(it.quantity) || 1,
                    unit: it.unit.trim() || 'porsiyon',
                    calories: Math.max(0, Math.round(parseFloat(it.calories) || 0)),
                    protein_g: Math.max(0, parseFloat((parseFloat(it.protein_g) || 0).toFixed(1))),
                    carbs_g: Math.max(0, parseFloat((parseFloat(it.carbs_g) || 0).toFixed(1))),
                    fat_g: Math.max(0, parseFloat((parseFloat(it.fat_g) || 0).toFixed(1))),
                }))
            };

            btnSave.disabled = true;
            btnSave.textContent = 'Kaydediliyor...';
            try {
                const created = await api.createMeal(payload);
                cleanup();
                showToast('Öğün başarıyla kaydedildi!', 'success');
                if (onSaveCallback) onSaveCallback(created);
            } catch (err) {
                btnSave.disabled = false;
                btnSave.innerHTML = `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"></polyline></svg> <span>Öğün Olarak Kaydet</span>`;
                showToast(err.message || 'Öğün kaydedilemedi.', 'error');
            }
        };

        dialog.showModal();
    }

    return {
        showToast,
        confirmDialog,
        formatNumber,
        formatDate,
        formatTime,
        translateMealType,
        openPhotoReviewModal,
    };
})();
