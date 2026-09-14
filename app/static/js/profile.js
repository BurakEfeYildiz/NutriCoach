/**
 * NutriCoach Profile, Security & Long-Term Memory View Logic
 */
document.addEventListener('DOMContentLoaded', async () => {
    const formProfile = document.getElementById('formProfile');
    const profBirthDate = document.getElementById('profBirthDate');
    const profSex = document.getElementById('profSex');
    const profHeight = document.getElementById('profHeight');
    const profGoalWeight = document.getElementById('profGoalWeight');
    const profActivityLevel = document.getElementById('profActivityLevel');
    const profWeeklyChange = document.getElementById('profWeeklyChange');
    const profCalories = document.getElementById('profCalories');
    const profProtein = document.getElementById('profProtein');
    const profCarbs = document.getElementById('profCarbs');
    const profFat = document.getElementById('profFat');

    const formChangePassword = document.getElementById('formChangePassword');
    const pwdCurrent = document.getElementById('pwdCurrent');
    const pwdNew = document.getElementById('pwdNew');
    const pwdConfirm = document.getElementById('pwdConfirm');
    const passwordAlert = document.getElementById('passwordAlert');
    const btnChangePassword = document.getElementById('btnChangePassword');

    const memoriesList = document.getElementById('memoriesList');
    const memoryCountBadge = document.getElementById('memoryCountBadge');

    await Promise.all([loadProfileData(), loadMemoriesData()]);

    async function loadProfileData() {
        try {
            const profile = await api.getProfile().catch(() => null);

            if (profile) {
                if (profile.birth_date) profBirthDate.value = profile.birth_date;
                if (profile.biological_sex) profSex.value = profile.biological_sex;
                if (profile.height_cm) profHeight.value = profile.height_cm;
                if (profile.goal_weight_kg) profGoalWeight.value = profile.goal_weight_kg;
                if (profile.activity_level) profActivityLevel.value = profile.activity_level;
                if (profile.preferred_weekly_weight_change_kg !== null && profile.preferred_weekly_weight_change_kg !== undefined) {
                    profWeeklyChange.value = profile.preferred_weekly_weight_change_kg;
                }
                if (profile.calorie_target) profCalories.value = profile.calorie_target;
                if (profile.protein_target_g) profProtein.value = profile.protein_target_g;
                if (profile.carb_target_g) profCarbs.value = profile.carb_target_g;
                if (profile.fat_target_g) profFat.value = profile.fat_target_g;
            }
        } catch (err) {
            console.error('Error loading profile data:', err);
            ui.showToast('Profil bilgileri yüklenemedi.', 'error');
        }
    }

    formProfile.addEventListener('submit', async (e) => {
        e.preventDefault();

        const payload = {
            birth_date: profBirthDate.value || null,
            biological_sex: profSex.value || 'unspecified',
            height_cm: profHeight.value ? parseFloat(profHeight.value) : null,
            goal_weight_kg: profGoalWeight.value ? parseFloat(profGoalWeight.value) : null,
            activity_level: profActivityLevel.value || null,
            calorie_target: profCalories.value ? parseInt(profCalories.value, 10) : null,
            protein_target_g: profProtein.value ? parseFloat(profProtein.value) : null,
            carb_target_g: profCarbs.value ? parseFloat(profCarbs.value) : null,
            fat_target_g: profFat.value ? parseFloat(profFat.value) : null,
            preferred_weekly_weight_change_kg: profWeeklyChange.value ? parseFloat(profWeeklyChange.value) : null,
        };

        try {
            await api.replaceProfile(payload);
            ui.showToast('Profil hedefleri kaydedildi.', 'success');
        } catch (err) {
            ui.showToast(err.message || 'Profil güncellenemedi.', 'error');
        }
    });

    if (formChangePassword) {
        formChangePassword.addEventListener('submit', async (e) => {
            e.preventDefault();
            passwordAlert.classList.add('hidden');

            const current = pwdCurrent.value;
            const newPw = pwdNew.value;
            const confirmPw = pwdConfirm.value;

            if (!current || !newPw || !confirmPw) {
                passwordAlert.textContent = 'Lütfen tüm şifre alanlarını doldurun.';
                passwordAlert.className = 'auth-alert auth-alert-error';
                passwordAlert.classList.remove('hidden');
                return;
            }

            if (newPw.length < 8) {
                passwordAlert.textContent = 'Yeni şifre en az 8 karakter olmalıdır.';
                passwordAlert.className = 'auth-alert auth-alert-error';
                passwordAlert.classList.remove('hidden');
                return;
            }

            if (newPw !== confirmPw) {
                passwordAlert.textContent = 'Yeni şifreler birbiriyle eşleşmiyor.';
                passwordAlert.className = 'auth-alert auth-alert-error';
                passwordAlert.classList.remove('hidden');
                return;
            }

            btnChangePassword.disabled = true;
            btnChangePassword.textContent = 'Güncelleniyor...';

            try {
                await api.changePassword(current, newPw);
                pwdCurrent.value = '';
                pwdNew.value = '';
                pwdConfirm.value = '';
                ui.showToast('Şifreniz başarıyla güncellendi.', 'success');
                passwordAlert.textContent = 'Şifreniz başarıyla güncellendi.';
                passwordAlert.className = 'auth-alert auth-alert-success';
                passwordAlert.classList.remove('hidden');
            } catch (err) {
                passwordAlert.textContent = err.message || 'Şifre güncellenemedi.';
                passwordAlert.className = 'auth-alert auth-alert-error';
                passwordAlert.classList.remove('hidden');
            } finally {
                btnChangePassword.disabled = false;
                btnChangePassword.textContent = 'Şifreyi Güncelle';
            }
        });
    }

    async function loadMemoriesData() {
        memoriesList.innerHTML = '<div class="skeleton-card"></div>';

        try {
            const memories = await api.listMemories();

            if (!memories || memories.length === 0) {
                memoryCountBadge.textContent = '0 kayıt';
                memoriesList.innerHTML = `
                    <div class="card empty-state-box">
                        <p>Koçun henüz hakkında özel bir tercih veya alışkanlık kaydetmedi.</p>
                        <p style="font-size: 0.8rem; margin-top: 6px;">Sohbet ederken sevdiklerini, sevmediklerini veya rutinlerini belirttikçe koçun bunları otomatik olarak hatırlar.</p>
                    </div>
                `;
                return;
            }

            memoryCountBadge.textContent = `${memories.length} kayıt`;

            memoriesList.innerHTML = memories.map(mem => {
                const categoryBadge = translateCategory(mem.category);
                return `
                    <div class="memory-item-card" id="mem-${mem.id}">
                        <div>
                            <span class="badge" style="font-size: 0.68rem; margin-bottom: 4px; display: inline-block;">${categoryBadge}</span>
                            <div class="memory-text">${mem.value}</div>
                        </div>
                        <button class="btn-forget btn-delete-mem" data-id="${mem.id}" aria-label="Hafızadan sil">
                            <span>Unut</span>
                        </button>
                    </div>
                `;
            }).join('');

            // Attach Delete Handlers
            document.querySelectorAll('.btn-delete-mem').forEach(btn => {
                btn.addEventListener('click', async () => {
                    const memId = btn.getAttribute('data-id');
                    const confirmed = await ui.confirmDialog(
                        'Hafızadan Kaldır',
                        'Bunu koçun hafızasından kaldırmak istediğinize emin misiniz?'
                    );
                    if (confirmed) {
                        try {
                            await api.deleteMemory(memId);
                            ui.showToast('Hafızadan kaldırıldı.', 'success');
                            await loadMemoriesData();
                        } catch (err) {
                            ui.showToast(err.message || 'Hafıza silinemedi.', 'error');
                        }
                    }
                });
            });

        } catch (err) {
            console.error('Error loading memories:', err);
            memoriesList.innerHTML = '<div class="card empty-state-box">Hafıza kayıtları yüklenemedi.</div>';
        }
    }

    function translateCategory(cat) {
        const map = {
            food_preference: 'Yemek Tercihi',
            food_dislike: 'Sevilmeyen Yiyecek',
            dietary_habit: 'Diyet Alışkanlığı',
            routine: 'Rutin',
            constraint: 'Kısıt',
        };
        return map[cat] || 'Tercih';
    }
});
