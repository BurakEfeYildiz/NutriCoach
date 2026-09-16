/**
 * NutriCoach Coach / Chat View Logic
 */
document.addEventListener("DOMContentLoaded", async () => {
  let conversationId = null;
  let pendingRetry = null; // { content, clientRequestId }

  const chatStream = document.getElementById("chatStream");
  const messagesList = document.getElementById("chatMessagesList");
  const chatInput = document.getElementById("chatInput");
  const chatForm = document.getElementById("chatForm");
  const btnSend = document.getElementById("btnSend");
  const typingIndicator = document.getElementById("typingIndicator");
  const welcomePlaceholder = document.getElementById("chatWelcome");
  const loadingHistory = document.getElementById("chatLoadingHistory");
  async function loadCoachContextLine() {
    try {
      const [daily, plan] = await Promise.all([api.getDailyNutrition(), api.getNutritionPlan()]);
      const line = document.getElementById("coachContextLine");
      if (!daily.has_records) line.textContent = plan.daily_calorie_target == null ? "Bugün için henüz öğün kaydı yok" : `Günlük hedef ${ui.formatNumber(plan.daily_calorie_target)} kcal · bugün henüz kayıt yok`;
      else line.textContent = daily.remaining_by_target?.calories == null ? "Bugünkü kayıtlarını görüyorum" : `Bugünkü hedefe göre kalan ${ui.formatNumber(daily.remaining_by_target.calories)} kcal${daily.remaining_by_target.protein_g == null ? "" : " · protein " + ui.formatNumber(daily.remaining_by_target.protein_g) + " g"}`;
    } catch (_) { document.getElementById("coachContextLine").textContent = "Koç, kayıtlarını yanıt verirken kullanır."; }
  }
  loadCoachContextLine();
  const coachDraft = sessionStorage.getItem("nutricoach_coach_draft");
  if (coachDraft && chatInput) {
    chatInput.value = coachDraft;
    sessionStorage.removeItem("nutricoach_coach_draft");
  }

  const updateViewport = () =>
    document.documentElement.style.setProperty(
      "--visual-height",
      `${window.visualViewport?.height || window.innerHeight}px`,
    );
  window.visualViewport?.addEventListener("resize", updateViewport);
  updateViewport();
  // Auto-expand textarea
  chatInput?.addEventListener("input", () => {
    chatInput.style.height = "auto";
    chatInput.style.height = `${Math.min(chatInput.scrollHeight, 120)}px`;
  });

  // Enter to send, Shift+Enter for newline
  chatInput?.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
      e.preventDefault();
      sendMessage();
    }
  });

  chatForm?.addEventListener("submit", (e) => {
    e.preventDefault();
    sendMessage();
  });

  // Photo input & analysis
  const btnCoachPhoto = document.getElementById("btnCoachPhoto");
  const coachPhotoInput = document.getElementById("coachPhotoInput");

  btnCoachPhoto?.addEventListener("click", () => {
    coachPhotoInput?.click();
  });

  coachPhotoInput?.addEventListener("change", async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    coachPhotoInput.value = "";

    if (file.size > 10 * 1024 * 1024) {
      ui.showToast("Fotoğraf boyutu 10MB'dan küçük olmalıdır.", "error");
      return;
    }

    btnCoachPhoto.disabled = true;

    try {
      const analysis = await ui.analyzePhoto(file);
      btnCoachPhoto.disabled = false;
      ui.openPhotoReviewModal(analysis, file, (createdMeal) => {
        appendMessageBubble({
          role: "assistant",
          content: `Fotoğraftan öğün kaydedildi: ${createdMeal.original_description || "Öğün"} (${ui.formatNumber(createdMeal.totals?.calories)} kcal)`,
          created_at: new Date().toISOString(),
          action_results: [{ type: "meal_create" }],
        });
        scrollToBottom();
      });
    } catch (err) {
      btnCoachPhoto.disabled = false;
      ui.showToast(err.message || "Fotoğraf analizi başarısız.", "error");
    }
  });

  // Chip suggestions
  document.querySelectorAll(".chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      const prompt = chip.getAttribute("data-prompt");
      if (prompt && chatInput) {
        chatInput.value = prompt;
        chatInput.focus();
        sendMessage();
      }
    });
  });

  // Initialize Conversation
  await initChat();

  async function initChat() {
    try {
      // Check existing conversations
      const conversations = await api.listConversations();
      if (conversations && conversations.length > 0) {
        conversationId = conversations[0].id;
      } else {
        const newConv = await api.createConversation();
        conversationId = newConv.id;
      }

      // Load message history
      const messages = await api.listMessages(conversationId);
      loadingHistory?.remove();

      if (!messages || messages.length === 0) {
        welcomePlaceholder.style.display = "block";
      } else {
        welcomePlaceholder.style.display = "none";
        messages.forEach((msg) => appendMessageBubble(msg));
        scrollToBottom();
      }
    } catch (err) {
      console.error("Chat init error:", err);
      loadingHistory?.remove();
      ui.showToast("Sohbet yüklenirken bir hata oluştu.", "error");
    }
  }

  async function sendMessage(retryPayload = null) {
    const text = retryPayload ? retryPayload.content : chatInput.value.trim();
    if (!text || !conversationId || btnSend.disabled) return;

    // Idempotency: use existing clientRequestId if retrying, otherwise generate a new UUIDv4
    const clientRequestId = retryPayload
      ? retryPayload.clientRequestId
      : crypto.randomUUID();

    if (!retryPayload) {
      chatInput.value = "";
      chatInput.style.height = "auto";
      welcomePlaceholder.style.display = "none";

      // Optimistically render user bubble
      appendMessageBubble({
        role: "user",
        content: text,
        created_at: new Date().toISOString(),
        status: "pending",
      });
    }

    btnSend.disabled = true;
    typingIndicator.style.display = "flex";
    scrollToBottom();

    try {
      const result = await api.sendMessage(
        conversationId,
        text,
        clientRequestId,
      );
      typingIndicator.style.display = "none";
      btnSend.disabled = false;
      pendingRetry = null;

      if (result.assistant_message) {
        appendMessageBubble(result.assistant_message, result.user_message);
      } else if (result.user_message?.effects_committed) {
        // Effects committed but assistant message failed
        appendMessageBubble(
          {
            role: "assistant",
            content:
              "İşleminiz başarıyla kaydedildi ancak koç yanıtı oluşturulamadı.",
            created_at: new Date().toISOString(),
            status: "completed",
          },
          result.user_message,
        );
      }
      if (
        !result.assistant_message &&
        !result.user_message?.effects_committed
      ) {
        pendingRetry = { content: text, clientRequestId };
        renderErrorBubble(
          "Koç şu an yanıt veremedi. Mesajını yeniden gönderebilirsin.",
          pendingRetry,
        );
      }
      scrollToBottom();
    } catch (err) {
      typingIndicator.style.display = "none";
      btnSend.disabled = false;

      // Safe retry tracking: reuse exact same clientRequestId to prevent double meal/weight creation
      pendingRetry = { content: text, clientRequestId };

      renderErrorBubble(
        "Bağlantı kurulamadı. Tekrar deneyebilirsiniz.",
        pendingRetry,
      );
      scrollToBottom();
    }
  }

  function appendMessageBubble(msg, userMsgContext = null) {
    const isUser = msg.role === "user";
    const wrapper = document.createElement("div");
    wrapper.className = `chat-bubble-wrapper ${isUser ? "bubble-user" : "bubble-assistant"}`;

    const bubble = document.createElement("div");
    bubble.className = "chat-bubble";
    if (isUser) bubble.textContent = msg.content;
    else {
      bubble.classList.add("rich-text");
      bubble.innerHTML = ui.richText(msg.content);
    }
    wrapper.setAttribute("aria-label", isUser ? "Sen" : "Beslenme koçun");
    wrapper.appendChild(bubble);

    // Render Action Confirmation Pill (e.g. meal created, weight recorded)
    const actions = userMsgContext?.action_results || msg.action_results || [];
    if (actions && actions.length > 0) {
      actions.forEach((act) => {
        const pill = document.createElement("div");
        pill.className = "action-pill";
        const label = translateActionType(act.type);
        pill.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><polyline points="20 6 9 17 4 12"></polyline></svg><span>${label}</span>`;
        wrapper.appendChild(pill);
      });
    }

    // Timestamp
    if (msg.created_at) {
      const timeEl = document.createElement("span");
      timeEl.className = "bubble-timestamp";
      timeEl.textContent = ui.formatTime(msg.created_at);
      wrapper.appendChild(timeEl);
    }

    // Render Grounding Sources Pill/List if present
    const sources = (msg.grounding_sources || []).filter((source) => {
      try {
        return ["https:", "http:"].includes(new URL(source.url).protocol);
      } catch (_) {
        return false;
      }
    });
    if (sources && sources.length > 0) {
      const groundCard = document.createElement("div");
      groundCard.className = "grounding-sources-card";
      groundCard.innerHTML = `
                <div class="grounding-badge">
                    <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="10"></circle><line x1="2" y1="12" x2="22" y2="12"></line><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"></path></svg>
                    <span>Google Arama kaynakları</span>
                </div>
                <div class="grounding-links">
                    ${sources.map((s) => `<a href="${ui.escapeHtml(s.url)}" target="_blank" rel="noopener noreferrer" class="grounding-link">${escapeHtml(s.title || "Kaynak")} &nearr;</a>`).join("")}
                </div>
            `;
      wrapper.appendChild(groundCard);
    }

    messagesList.appendChild(wrapper);
  }

  function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text || "";
    return div.innerHTML;
  }

  function renderErrorBubble(errorText, retryData) {
    const wrapper = document.createElement("div");
    wrapper.className = "chat-bubble-wrapper bubble-assistant";

    const bubble = document.createElement("div");
    bubble.className = "chat-bubble";
    bubble.classList.add("chat-bubble-error");
    bubble.textContent = errorText;

    const retryBtn = document.createElement("button");
    retryBtn.className = "btn btn-sm btn-secondary";

    retryBtn.textContent = "Tekrar Dene";
    retryBtn.addEventListener("click", () => {
      wrapper.remove();
      sendMessage(retryData);
    });

    bubble.appendChild(document.createElement("br"));
    bubble.appendChild(retryBtn);
    wrapper.appendChild(bubble);
    messagesList.appendChild(wrapper);
  }

  function translateActionType(type) {
    const map = {
      meal_create: "Öğün günlüğüne eklendi",
      meal_replace: "Öğün güncellendi",
      meal_delete: "Öğün silindi",
      weight_log_create: "Kilo günlüğüne kaydedildi",
      profile_replace: "Profil hedefleri güncellendi",
    };
    return map[type] || "Kayıt işlendi";
  }

  function scrollToBottom() {
    chatStream.scrollTop = chatStream.scrollHeight;
  }
});
