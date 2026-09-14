/**
 * NutriCoach API Client — Centralized authenticated fetch client
 */
const api = (() => {
    const BASE_URL = '/api/v1';

    function getCsrfToken() {
        return document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';
    }

    async function apiFetch(endpoint, options = {}) {
        const url = endpoint.startsWith('http') ? endpoint : `${BASE_URL}${endpoint}`;
        const method = (options.method || 'GET').toUpperCase();
        const headers = {
            'Content-Type': 'application/json',
            ...(options.headers || {}),
        };

        // Attach CSRF token on state-changing requests
        if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(method)) {
            const csrfToken = getCsrfToken();
            if (csrfToken) {
                headers['X-CSRF-Token'] = csrfToken;
            }
        }

        const config = {
            ...options,
            method,
            headers,
            credentials: 'same-origin',
        };

        if (options.body && typeof options.body === 'object') {
            config.body = JSON.stringify(options.body);
        }

        try {
            const response = await fetch(url, config);
            if (response.status === 204) {
                return null;
            }

            // Handle unauthorized 401 -> redirect to login
            if (response.status === 401) {
                if (!window.location.pathname.startsWith('/login') && !window.location.pathname.startsWith('/register')) {
                    window.location.href = '/login?expired=1';
                    return null;
                }
            }

            const data = await response.json().catch(() => null);
            if (!response.ok) {
                const error = new Error(data?.detail || `API Hatası (${response.status})`);
                error.status = response.status;
                error.data = data;
                throw error;
            }
            return data;
        } catch (err) {
            console.error('API Error:', err);
            throw err;
        }
    }

    return {
        apiFetch,

        // Authentication
        async login(email, password) {
            return apiFetch('/auth/login', {
                method: 'POST',
                body: { email, password },
            });
        },
        async register(name, email, password, timezone = 'Europe/Istanbul') {
            return apiFetch('/auth/register', {
                method: 'POST',
                body: { name, email, password, timezone },
            });
        },
        async logout() {
            return apiFetch('/auth/logout', {
                method: 'POST',
            });
        },
        async getMe() {
            return apiFetch('/me');
        },

        // User & Profile
        async getProfile() {
            return apiFetch('/me/profile');
        },
        async replaceProfile(profileData) {
            return apiFetch('/me/profile', {
                method: 'PUT',
                body: profileData,
            });
        },
        async changePassword(currentPassword, newPassword) {
            return apiFetch('/me/change-password', {
                method: 'POST',
                body: {
                    current_password: currentPassword,
                    new_password: newPassword,
                },
            });
        },

        // Nutrition & Meals
        async getDailyNutrition(day = null) {
            const query = day ? `?day=${day}` : '';
            return apiFetch(`/me/nutrition/daily${query}`);
        },
        async getWeeklyNutrition(endDay = null) {
            const query = endDay ? `?end_day=${endDay}` : '';
            return apiFetch(`/me/nutrition/weekly${query}`);
        },
        async listMeals(day = null) {
            const query = day ? `?day=${day}` : '';
            return apiFetch(`/me/meals${query}`);
        },
        async getTodayMeals() {
            return apiFetch('/me/meals/today');
        },
        async analyzeMealPhoto(file) {
            const formData = new FormData();
            formData.append('file', file);
            const headers = {};
            const csrfToken = getCsrfToken();
            if (csrfToken) {
                headers['X-CSRF-Token'] = csrfToken;
            }
            const response = await fetch(`${BASE_URL}/me/meals/analyze-photo`, {
                method: 'POST',
                headers,
                body: formData,
                credentials: 'same-origin',
            });
            if (response.status === 401) {
                if (!window.location.pathname.startsWith('/login') && !window.location.pathname.startsWith('/register')) {
                    window.location.href = '/login?expired=1';
                    return null;
                }
            }
            const data = await response.json().catch(() => null);
            if (!response.ok) {
                const error = new Error(data?.detail || `Fotoğraf analizi başarısız (${response.status})`);
                error.status = response.status;
                error.data = data;
                throw error;
            }
            return data;
        },
        async createMeal(mealData) {
            return apiFetch('/me/meals', {
                method: 'POST',
                body: mealData,
            });
        },
        async replaceMeal(mealId, mealData) {
            return apiFetch(`/me/meals/${mealId}`, {
                method: 'PUT',
                body: mealData,
            });
        },
        async deleteMeal(mealId) {
            return apiFetch(`/me/meals/${mealId}`, {
                method: 'DELETE',
            });
        },

        // Weights
        async getCurrentWeight() {
            return apiFetch('/me/weight-logs/current');
        },
        async listWeights(limit = 100) {
            return apiFetch(`/me/weight-logs?limit=${limit}`);
        },
        async createWeight(data) {
            return apiFetch('/me/weight-logs', {
                method: 'POST',
                body: data,
            });
        },
        async deleteWeight(weightId) {
            return apiFetch(`/me/weight-logs/${weightId}`, {
                method: 'DELETE',
            });
        },

        // Memories
        async listMemories(includeInactive = false) {
            return apiFetch(`/me/memories?include_inactive=${includeInactive}`);
        },
        async deleteMemory(memoryId) {
            return apiFetch(`/me/memories/${memoryId}`, {
                method: 'DELETE',
            });
        },

        // Chat
        async listConversations() {
            return apiFetch('/me/conversations');
        },
        async createConversation() {
            return apiFetch('/me/conversations', {
                method: 'POST',
            });
        },
        async listMessages(conversationId) {
            return apiFetch(`/me/conversations/${conversationId}/messages`);
        },
        async sendMessage(conversationId, content, clientRequestId) {
            return apiFetch(`/me/conversations/${conversationId}/messages`, {
                method: 'POST',
                body: {
                    content,
                    client_request_id: clientRequestId,
                },
            });
        },
    };
})();
