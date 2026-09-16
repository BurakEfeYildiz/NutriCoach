/**
 * NutriCoach UI Utilities — Toasts, Dialogs, and Presentation Formatting
 */
const ui = (() => {
  function showToast(message, type = "success", durationMs = 3500) {
    const container = document.getElementById("toastContainer");
    if (!container) return;

    const toast = document.createElement("div");
    toast.className = `toast toast-${type}`;

    const iconSvg =
      type === "success"
        ? `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><polyline points="20 6 9 17 4 12"></polyline></svg>`
        : `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>`;

    toast.innerHTML = `${iconSvg}<span>${escapeHtml(message)}</span>`;
    container.appendChild(toast);

    setTimeout(() => {
      toast.classList.add("toast-leaving");
      setTimeout(() => toast.remove(), 250);
    }, durationMs);
  }

  function confirmDialog(title, message) {
    return new Promise((resolve) => {
      const dialog = document.getElementById("confirmDialog");
      const titleEl = document.getElementById("confirmDialogTitle");
      const msgEl = document.getElementById("confirmDialogMessage");
      const cancelBtn = document.getElementById("confirmDialogCancel");
      const confirmBtn = document.getElementById("confirmDialogConfirm");

      if (!dialog) {
        resolve(window.confirm(`${title}\n\n${message}`));
        return;
      }

      titleEl.textContent = title;
      msgEl.textContent = message;

      function cleanup() {
        cancelBtn.removeEventListener("click", onCancel);
        confirmBtn.removeEventListener("click", onConfirm);
        dialog.removeEventListener("cancel", onCancel);
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

      cancelBtn.addEventListener("click", onCancel);
      confirmBtn.addEventListener("click", onConfirm);

      dialog.addEventListener("cancel", onCancel);
      dialog.showModal();
    });
  }

  function formatNumber(value, decimals = 0) {
    if (value === null || value === undefined || isNaN(value)) return "—";
    const num = Number(value);
    return num.toLocaleString("tr-TR", {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    });
  }

  function formatCompactNumber(value) {
    if (value === null || value === undefined || isNaN(value)) return "—";
    const fraction = Number(value).toFixed(2).split(".")[1];
    return formatNumber(value, fraction === "00" ? 0 : fraction.endsWith("0") ? 1 : 2);
  }

  function localizeDecimalText(value) {
    return String(value || "").replace(/\b(\d+)\.(\d{2})\b/g, (_, whole, fraction) =>
      formatNumber(Number(`${whole}.${fraction}`), fraction === "00" ? 0 : fraction.endsWith("0") ? 1 : 2));
  }

  function formatDate(dateStr) {
    if (!dateStr) return "";
    // Date format: YYYY-MM-DD
    const parts = dateStr.split("-");
    if (parts.length === 3) {
      const date = new Date(parts[0], parts[1] - 1, parts[2]);
      return date.toLocaleDateString("tr-TR", {
        day: "numeric",
        month: "long",
        weekday: "long",
      });
    }
    return dateStr;
  }

  function formatTime(isoStr) {
    if (!isoStr) return "";
    try {
      const date = new Date(isoStr);
      return date.toLocaleTimeString("tr-TR", {
        hour: "2-digit",
        minute: "2-digit",
        timeZone:
          document.documentElement.dataset.timezone || "Europe/Istanbul",
      });
    } catch (e) {
      return "";
    }
  }

  function translateMealType(type) {
    const map = {
      breakfast: "Kahvaltı",
      lunch: "Öğle Yemeği",
      dinner: "Akşam Yemeği",
      snack: "Ara Öğün",
      extra: "Ekstra",
      other: "Öğün",
    };
    return map[type] || "Öğün";
  }

  function openPhotoReviewModal(
    analysis,
    imageFile,
    onSaveCallback,
    existingMeal = null,
  ) {
    const dialog = document.getElementById("modalPhotoMealReview");
    if (!dialog) return;

    const imgPreviewContainer = document.getElementById(
      "photoPreviewContainer",
    );
    const imgPreview = document.getElementById("photoPreviewImg");
    const mealTypeSelect = document.getElementById("photoMealType");
    const mealDescInput = document.getElementById("photoMealDescription");
    const confidenceEl = document.getElementById("photoMealConfidence");
    const itemsList = document.getElementById("photoItemsList");
    document.getElementById("mealReviewTitle").textContent = existingMeal
      ? "Öğünü düzenle"
      : "Fotoğraftan öğün tahmini";
    dialog.setAttribute(
      "aria-label",
      existingMeal ? "Öğünü düzenle" : "Fotoğraftan öğün",
    );
    dialog.querySelector(".photo-disclaimer-note").hidden =
      Boolean(existingMeal);
    const btnAdd = document.getElementById("btnAddPhotoItem");
    const btnClose = document.getElementById("btnClosePhotoMeal");
    const btnCancel = document.getElementById("btnCancelPhotoMeal");
    const btnSave = document.getElementById("btnConfirmSavePhotoMeal");

    let objectUrl = null;
    if (imageFile) {
      objectUrl = URL.createObjectURL(imageFile);
      imgPreview.src = objectUrl;
      imgPreviewContainer.style.display = "block";
    } else {
      imgPreviewContainer.style.display = "none";
    }

    mealTypeSelect.value = analysis.meal_type || "lunch";
    mealDescInput.value =
      existingMeal?.original_description ||
      (analysis.items || []).map((item) => item.name).join(", ");
    if (analysis.confidence) {
      confidenceEl.textContent = `Tahmin güveni: %${formatNumber(Number(analysis.confidence) * 100)}`;
    } else {
      confidenceEl.textContent = existingMeal
        ? "Besin değerlerini kontrol et"
        : "Yapay zekâ tahmini";
    }

    const warningBox = document.getElementById("photoAnalysisWarnings");
    if (warningBox) {
      warningBox.textContent = (analysis.warnings || []).join(" ");
      warningBox.hidden = !warningBox.textContent;
    }

    let items = (analysis.items || []).map((item) => ({
      name: item.name || "",
      quantity: item.quantity ?? 1,
      unit: item.unit || "porsiyon",
      calories: item.calories ?? 0,
      protein_g: item.protein_g ?? 0,
      carbs_g: item.carbs_g ?? 0,
      fat_g: item.fat_g ?? 0,
      assumptions: item.assumptions ?? null,
    }));

    function updateTotals() {
      let totalCal = 0;
      let totalP = 0;
      let totalC = 0;
      let totalF = 0;
      items.forEach((it) => {
        totalCal += parseFloat(it.calories) || 0;
        totalP += parseFloat(it.protein_g) || 0;
        totalC += parseFloat(it.carbs_g) || 0;
        totalF += parseFloat(it.fat_g) || 0;
      });
      const calEl = document.getElementById("photoTotalCalories");
      const pEl = document.getElementById("photoTotalProtein");
      const cEl = document.getElementById("photoTotalCarbs");
      const fEl = document.getElementById("photoTotalFat");
      if (calEl) calEl.textContent = `${formatNumber(totalCal)} kcal`;
      if (pEl) pEl.textContent = formatNumber(totalP, 1);
      if (cEl) cEl.textContent = formatNumber(totalC, 1);
      if (fEl) fEl.textContent = formatNumber(totalF, 1);
    }

    function renderItems() {
      itemsList.innerHTML = "";
      if (items.length === 0) {
        itemsList.innerHTML =
          '<p class="empty-hint">Henüz yiyecek eklenmedi.</p>';
        updateTotals();
        return;
      }

      items.forEach((item, index) => {
        const card = document.createElement("div");
        card.className = "photo-item-card";
        card.innerHTML = `
                    <div class="photo-item-main-row">
                        <input type="text" class="form-control item-name" aria-label="Yiyecek adı" placeholder="Yiyecek adı" required maxlength="200" value="${escapeHtml(item.name)}">
                        <button type="button" class="btn-remove-item" title="Yiyeceği kaldır" aria-label="Yiyeceği kaldır">&times;</button>
                    </div>
                    <div class="photo-item-fields-grid">
                        <div class="field-col">
                            <label>Miktar</label>
                            <input type="number" class="form-control item-qty" value="${item.quantity}" step="0.1" min="0.01">
                        </div>
                        <div class="field-col">
                            <label>Birim</label>
                            <input type="text" class="form-control item-unit" value="${escapeHtml(item.unit)}">
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
                            <label>Karbonhidrat (g)</label>
                            <input type="number" class="form-control item-c" value="${item.carbs_g}" min="0" step="0.1">
                        </div>
                        <div class="field-col">
                            <label>Yağ (g)</label>
                            <input type="number" class="form-control item-f" value="${item.fat_g}" min="0" step="0.1">
                        </div>
                    </div>
                `;

        card.querySelectorAll(".field-col").forEach((field, fieldIndex) => {
          const input = field.querySelector("input");
          input.id = `photo-item-${index}-${fieldIndex}`;
          field.querySelector("label").htmlFor = input.id;
          input.required = true;
          if (input.type === "number") {
            input.max = "1000000";
            input.step = "0.01";
          } else input.maxLength = 30;
        });
        const nameInput = card.querySelector(".item-name");
        const qtyInput = card.querySelector(".item-qty");
        const unitInput = card.querySelector(".item-unit");
        const calInput = card.querySelector(".item-cal");
        const pInput = card.querySelector(".item-p");
        const cInput = card.querySelector(".item-c");
        const fInput = card.querySelector(".item-f");
        const btnRemove = card.querySelector(".btn-remove-item");

        nameInput.addEventListener("input", () => {
          item.name = nameInput.value;
        });
        qtyInput.addEventListener("input", () => {
          item.quantity = parseFloat(qtyInput.value) || 0;
        });
        unitInput.addEventListener("input", () => {
          item.unit = unitInput.value;
        });
        calInput.addEventListener("input", () => {
          item.calories = parseFloat(calInput.value) || 0;
          updateTotals();
        });
        pInput.addEventListener("input", () => {
          item.protein_g = parseFloat(pInput.value) || 0;
          updateTotals();
        });
        cInput.addEventListener("input", () => {
          item.carbs_g = parseFloat(cInput.value) || 0;
          updateTotals();
        });
        fInput.addEventListener("input", () => {
          item.fat_g = parseFloat(fInput.value) || 0;
          updateTotals();
        });
        btnRemove.addEventListener("click", () => {
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
      btnSave.innerHTML = `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8"><polyline points="20 6 9 17 4 12"></polyline></svg> <span>Öğün Olarak Kaydet</span>`;
      dialog.removeEventListener("cancel", cleanup);
      dialog.removeEventListener("close", cleanup);
      if (dialog.open) dialog.close();
    }

    dialog.addEventListener("cancel", cleanup);
    dialog.addEventListener("close", cleanup);
    btnAdd.onclick = () => {
      items.push({
        name: "",
        quantity: 1,
        unit: "porsiyon",
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
        showToast("Lütfen en az bir yiyecek ekleyin.", "error");
        return;
      }
      for (const input of dialog.querySelectorAll("input")) {
        if (!input.reportValidity()) return;
      }
      const desc = mealDescInput.value.trim() || "Öğün";
      const payload = {
        meal_type: mealTypeSelect.value,
        occurred_at: existingMeal?.occurred_at || new Date().toISOString(),
        original_description: desc,
        nutrition_source: "user_corrected",
        normalized_description: existingMeal?.normalized_description ?? null,
        confidence: existingMeal?.confidence ?? analysis.confidence ?? null,
        items: items.map((it) => ({
          name: it.name.trim() || "Yiyecek",
          quantity: parseFloat(it.quantity) || 1,
          unit: it.unit.trim() || "porsiyon",
          calories: Number(Number(it.calories).toFixed(2)),
          source: "user_corrected",
          assumptions: it.assumptions,
          protein_g: Math.max(
            0,
            parseFloat((parseFloat(it.protein_g) || 0).toFixed(2)),
          ),
          carbs_g: Math.max(
            0,
            parseFloat((parseFloat(it.carbs_g) || 0).toFixed(2)),
          ),
          fat_g: Math.max(
            0,
            parseFloat((parseFloat(it.fat_g) || 0).toFixed(2)),
          ),
        })),
      };

      btnSave.disabled = true;
      btnSave.textContent = "Kaydediliyor...";
      try {
        const created = existingMeal
          ? await api.replaceMeal(existingMeal.id, {
              ...payload,
              expected_version: existingMeal.version,
            })
          : await api.createMeal(payload);
        cleanup();
        showToast("Öğün başarıyla kaydedildi!", "success");
        if (onSaveCallback) onSaveCallback(created);
      } catch (err) {
        btnSave.disabled = false;
        btnSave.innerHTML = `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8"><polyline points="20 6 9 17 4 12"></polyline></svg> <span>Öğün Olarak Kaydet</span>`;
        showToast(err.message || "Öğün kaydedilemedi.", "error");
      }
    };

    dialog.showModal();
  }

  function escapeHtml(value) {
    return String(value ?? "").replace(
      /[&<>"']/g,
      (char) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;",
        })[char],
    );
  }

  function localDate(value = new Date()) {
    const parts = new Intl.DateTimeFormat("en-CA", {
      timeZone: document.documentElement.dataset.timezone || "Europe/Istanbul",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).formatToParts(new Date(value));
    const get = (type) => parts.find((part) => part.type === type).value;
    return `${get("year")}-${get("month")}-${get("day")}`;
  }

  // Supported rich text is constructed from escaped text; arbitrary HTML is never executed.
  function richText(content) {
    const inline = (text) =>
      escapeHtml(text).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
    return String(content || "")
      .split(/\n\s*\n/)
      .map((block) => {
        const lines = block.split("\n");
        if (lines.every((line) => /^\s*[-*]\s+/.test(line)))
          return (
            "<ul>" +
            lines
              .map(
                (line) =>
                  "<li>" + inline(line.replace(/^\s*[-*]\s+/, "")) + "</li>",
              )
              .join("") +
            "</ul>"
          );
        if (lines.every((line) => /^\s*\d+\.\s+/.test(line)))
          return (
            "<ol>" +
            lines
              .map(
                (line) =>
                  "<li>" + inline(line.replace(/^\s*\d+\.\s+/, "")) + "</li>",
              )
              .join("") +
            "</ol>"
          );
        return (
          "<p>" +
          lines
            .map((line) => inline(line.replace(/^#{1,6}\s+/, "")))
            .join("<br>") +
          "</p>"
        );
      })
      .join("");
  }

  async function analyzePhoto(file) {
    const controller = new AbortController();
    const cancel = () => controller.abort();
    const cancelButton = document.getElementById("btnCancelScan");
    cancelButton?.addEventListener("click", cancel);
    const dialog = document.getElementById("photoScanningDialog");
    const preview = document.getElementById("scanningPreview");
    let objectUrl;
    if (dialog && preview) {
      objectUrl = URL.createObjectURL(file);
      preview.src = objectUrl;
      dialog.addEventListener("cancel", cancel);
      dialog.showModal();
    }
    try {
      return await api.analyzeMealPhoto(file, controller.signal);
    } catch (error) {
      if (error.name === "AbortError")
        throw new Error("Fotoğraf analizi iptal edildi.");
      throw error;
    } finally {
      dialog?.removeEventListener("cancel", cancel);
      cancelButton?.removeEventListener("click", cancel);
      if (dialog?.open) dialog.close();
      if (preview) preview.removeAttribute("src");
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    }
  }

  // --- Theme Management ---
  function getThemeSetting() {
    try {
      return localStorage.getItem("nutricoach_theme") || "system";
    } catch (_) {
      return document.documentElement.dataset.themeSetting || "system";
    }
  }

  function updateThemeSwitcherUI(mode) {
    document.querySelectorAll("[data-theme-btn]").forEach((btn) => {
      const btnTheme = btn.getAttribute("data-theme-btn");
      if (btnTheme === mode) {
        btn.classList.add("active");
        btn.setAttribute("aria-pressed", "true");
      } else {
        btn.classList.remove("active");
        btn.setAttribute("aria-pressed", "false");
      }
    });
    const select = document.getElementById("themeSelect");
    if (select && select.value !== mode) {
      select.value = mode;
    }
  }

  function setTheme(mode) {
    const validModes = ["light", "dark", "system"];
    const chosen = validModes.includes(mode) ? mode : "system";
    try {
      localStorage.setItem("nutricoach_theme", chosen);
    } catch (_) {}

    let resolved = chosen;
    if (chosen === "system") {
      resolved = window.matchMedia("(prefers-color-scheme: dark)").matches
        ? "dark"
        : "light";
    }
    document.documentElement.setAttribute("data-theme", resolved);
    document.documentElement.setAttribute("data-theme-setting", chosen);

    // Update meta theme-color for mobile browser chrome
    const metaThemeColor = document.querySelector('meta[name="theme-color"]');
    if (metaThemeColor) {
      metaThemeColor.setAttribute(
        "content",
        getComputedStyle(document.documentElement)
          .getPropertyValue("--color-bg")
          .trim(),
      );
    }

    updateThemeSwitcherUI(chosen);
  }

  function initTheme() {
    const current = getThemeSetting();
    setTheme(current);

    // Listen for OS scheme changes in system mode
    window
      .matchMedia("(prefers-color-scheme: dark)")
      .addEventListener("change", (e) => {
        if (getThemeSetting() === "system") {
          const resolved = e.matches ? "dark" : "light";
          document.documentElement.setAttribute("data-theme", resolved);
          const metaThemeColor = document.querySelector(
            'meta[name="theme-color"]',
          );
          if (metaThemeColor) {
            metaThemeColor.setAttribute(
              "content",
              getComputedStyle(document.documentElement)
                .getPropertyValue("--color-bg")
                .trim(),
            );
          }
        }
      });

    document
      .getElementById("mobileThemeToggle")
      ?.addEventListener("click", () => {
        setTheme(
          document.documentElement.dataset.theme === "dark" ? "light" : "dark",
        );
      });
    // Delegate theme button clicks
    document.addEventListener("click", (e) => {
      const btn = e.target.closest("[data-theme-btn]");
      if (btn) {
        const targetTheme = btn.getAttribute("data-theme-btn");
        setTheme(targetTheme);
      }
    });

    // Delegate theme dropdown changes if present
    const select = document.getElementById("themeSelect");
    if (select) {
      select.addEventListener("change", (e) => setTheme(e.target.value));
    }
  }

  // Auto-init theme UI on DOMContentLoaded
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initTheme);
  } else {
    initTheme();
  }

  return {
    escapeHtml,
    localDate,
    richText,
    analyzePhoto,
    showToast,
    confirmDialog,
    formatNumber,
    formatCompactNumber,
    localizeDecimalText,
    formatDate,
    formatTime,
    translateMealType,
    openPhotoReviewModal,
    getThemeSetting,
    setTheme,
    initTheme,
  };
})();
