/**
 * NutriCoach API Client — Centralized authenticated fetch client
 */
const api = (() => {
  const BASE_URL = "/api/v1";

  function errorMessage(detail, status) {
    if (Array.isArray(detail))
      return "Bazı alanlar geçerli değil. Bilgilerini kontrol edip yeniden dene.";
    if (typeof detail === "string" && /[çğıöşüÇĞİÖŞÜ]/.test(detail))
      return detail;
    return (
      {
        401: "E-posta veya şifre hatalı. Lütfen yeniden dene.",
        403: "İşlem doğrulanamadı. Sayfayı yenileyip tekrar dene.",
        409: "Bu kayıt değişmiş olabilir. Sayfayı yenileyip kontrol et.",
        422: "Bilgilerini kontrol edip yeniden dene.",
        429: "Çok fazla deneme yaptın. Biraz bekleyip tekrar dene.",
        503: "Hizmete şu an ulaşılamıyor. Biraz sonra yeniden dene.",
      }[status] || "İşlem tamamlanamadı. Lütfen yeniden dene."
    );
  }

  function getCsrfToken() {
    return (
      document
        .querySelector('meta[name="csrf-token"]')
        ?.getAttribute("content") || ""
    );
  }

  async function apiFetch(endpoint, options = {}) {
    const url = endpoint.startsWith("http")
      ? endpoint
      : `${BASE_URL}${endpoint}`;
    const method = (options.method || "GET").toUpperCase();
    const headers = {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    };

    // Attach CSRF token on state-changing requests
    if (["POST", "PUT", "PATCH", "DELETE"].includes(method)) {
      const csrfToken = getCsrfToken();
      if (csrfToken) {
        headers["X-CSRF-Token"] = csrfToken;
      }
    }

    const config = {
      ...options,
      method,
      headers,
      credentials: "same-origin",
    };

    if (options.body && typeof options.body === "object") {
      config.body = JSON.stringify(options.body);
    }

    try {
      const response = await fetch(url, config);
      if (response.status === 204) {
        return null;
      }

      // Handle unauthorized 401 -> redirect to login
      if (response.status === 401) {
        if (
          !window.location.pathname.startsWith("/login") &&
          !window.location.pathname.startsWith("/register")
        ) {
          window.location.href = "/login?expired=1";
          return null;
        }
      }

      const data = await response.json().catch(() => null);
      if (!response.ok) {
        const error = new Error(errorMessage(data?.detail, response.status));
        error.status = response.status;
        error.data = data;
        throw error;
      }
      return data;
    } catch (err) {
      console.error("API Error:", err);
      throw err;
    }
  }

  return {
    apiFetch,

    // Authentication
    async login(email, password) {
      return apiFetch("/auth/login", {
        method: "POST",
        body: { email, password },
      });
    },
    async register(name, email, password, timezone = "Europe/Istanbul") {
      return apiFetch("/auth/register", {
        method: "POST",
        body: { name, email, password, timezone },
      });
    },
    async logout() {
      return apiFetch("/auth/logout", {
        method: "POST",
      });
    },
    async getMe() {
      return apiFetch("/me");
    },

    // User & Profile
    async getProfile() {
      return apiFetch("/me/profile");
    },
    async replaceProfile(profileData) {
      return apiFetch("/me/profile", {
        method: "PUT",
        body: profileData,
      });
    },
    async updateAccount(accountData) {
      return apiFetch("/me/account", { method: "PATCH", body: accountData });
    },
    async getOnboarding() {
      return apiFetch("/me/onboarding");
    },
    async completeOnboarding(data) {
      return apiFetch("/me/onboarding", { method: "PUT", body: data });
    },
    async getNutritionPlan() {
      return apiFetch("/me/nutrition-plan");
    },
    async updateNutritionProfile(data) {
      return apiFetch("/me/nutrition-profile", { method: "PUT", body: data });
    },
    async changePassword(currentPassword, newPassword) {
      return apiFetch("/me/change-password", {
        method: "POST",
        body: {
          current_password: currentPassword,
          new_password: newPassword,
        },
      });
    },

    // Nutrition & Meals
    async getDailyNutrition(day = null) {
      const query = day ? `?day=${day}` : "";
      return apiFetch(`/me/nutrition/daily${query}`);
    },
    async getWeeklyNutrition(endDay = null) {
      const query = endDay ? `?end_day=${endDay}` : "";
      return apiFetch(`/me/nutrition/weekly${query}`);
    },
    async getAdaptiveDashboard() { return apiFetch("/me/adaptive-dashboard"); },
    async getRecommendedRecipes(mealType = null) {
      const query = mealType ? `?meal_type=${encodeURIComponent(mealType)}` : "";
      return apiFetch(`/me/recipes/recommended${query}`);
    },
    async getRecipe(recipeId) { return apiFetch(`/me/recipes/${recipeId}`); },
    async getDietaryExclusions() { return apiFetch("/me/dietary-exclusions"); },
    async putDietaryExclusions(foods) { return apiFetch("/me/dietary-exclusions", { method: "PUT", body: { foods } }); },
    async listMeals(day = null) {
      const query = day ? `?day=${day}` : "";
      return apiFetch(`/me/meals${query}`);
    },
    async getTodayMeals() {
      return apiFetch("/me/meals/today");
    },
    async analyzeMealPhoto(file, signal) {
      const formData = new FormData();
      formData.append("file", file);
      const headers = {};
      const csrfToken = getCsrfToken();
      if (csrfToken) {
        headers["X-CSRF-Token"] = csrfToken;
      }
      const response = await fetch(`${BASE_URL}/me/meals/analyze-photo`, {
        method: "POST",
        headers,
        body: formData,
        signal,
        credentials: "same-origin",
      });
      if (response.status === 401) {
        if (
          !window.location.pathname.startsWith("/login") &&
          !window.location.pathname.startsWith("/register")
        ) {
          window.location.href = "/login?expired=1";
          return null;
        }
      }
      const data = await response.json().catch(() => null);
      if (!response.ok) {
        const error = new Error(errorMessage(data?.detail, response.status));
        error.status = response.status;
        error.data = data;
        throw error;
      }
      return data;
    },
    async createMeal(mealData) {
      return apiFetch("/me/meals", {
        method: "POST",
        body: mealData,
      });
    },
    async replaceMeal(mealId, mealData) {
      return apiFetch(`/me/meals/${mealId}`, {
        method: "PUT",
        body: mealData,
      });
    },
    async deleteMeal(mealId) {
      return apiFetch(`/me/meals/${mealId}`, {
        method: "DELETE",
      });
    },
    async searchFoods(query, includeExternal = false) { return apiFetch(`/me/foods/search?q=${encodeURIComponent(query)}&include_external=${includeExternal}`); },
    async recentFoods() { return apiFetch("/me/foods/recent"); },
    async favoriteFoods() { return apiFetch("/me/foods/favorites"); },
    async cacheExternalFood(sourceFoodId) { return apiFetch("/me/foods/external-cache", { method: "POST", body: { source: "open_food_facts", source_food_id: sourceFoodId } }); },
    async createCustomFood(data) { return apiFetch("/me/foods", { method: "POST", body: data }); },
    async previewFood(data) { return apiFetch("/me/foods/log-preview", { method: "POST", body: data }); },
    async logFood(data) { return apiFetch("/me/foods/log", { method: "POST", body: data }); },
    async favoriteFood(foodId) { return apiFetch(`/me/foods/${foodId}/favorite`, { method: "PUT" }); },

    // Weights
    async getCurrentWeight() {
      return apiFetch("/me/weight-logs/current");
    },
    async listWeights(limit = 100) {
      return apiFetch(`/me/weight-logs?limit=${limit}`);
    },
    async createWeight(data) {
      return apiFetch("/me/weight-logs", {
        method: "POST",
        body: data,
      });
    },
    async deleteWeight(weightId) {
      return apiFetch(`/me/weight-logs/${weightId}`, {
        method: "DELETE",
      });
    },
    async getTodayActivity() { return apiFetch("/me/activity/today"); },
    async putDailySteps(data) { return apiFetch("/me/daily-steps", { method: "PUT", body: data }); },
    async createWorkout(data) { return apiFetch("/me/workouts", { method: "POST", body: data }); },
    async deleteWorkout(id) { return apiFetch(`/me/workouts/${id}`, { method: "DELETE" }); },

    // Memories
    async listMemories(includeInactive = false) {
      return apiFetch(`/me/memories?include_inactive=${includeInactive}`);
    },
    async deleteMemory(memoryId) {
      return apiFetch(`/me/memories/${memoryId}`, {
        method: "DELETE",
      });
    },

    // Chat
    async listConversations() {
      return apiFetch("/me/conversations");
    },
    async createConversation() {
      return apiFetch("/me/conversations", {
        method: "POST",
      });
    },
    async listMessages(conversationId) {
      return apiFetch(`/me/conversations/${conversationId}/messages`);
    },
    async sendMessage(conversationId, content, clientRequestId) {
      return apiFetch(`/me/conversations/${conversationId}/messages`, {
        method: "POST",
        body: {
          content,
          client_request_id: clientRequestId,
        },
      });
    },
  };
})();
