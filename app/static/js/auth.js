document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("[data-password-toggle]").forEach((button) =>
    button.addEventListener("click", () => {
      const input = document.getElementById(button.dataset.passwordToggle);
      const show = input.type === "password";
      input.type = show ? "text" : "password";
      button.setAttribute("aria-pressed", String(show));
      button.setAttribute(
        "aria-label",
        show ? "Şifreyi gizle" : "Şifreyi göster",
      );
    }),
  );
  const form = document.querySelector("[data-auth]");
  const alert = document.getElementById("authAlert");
  const report = (message) => {
    alert.textContent = message;
    alert.className = "auth-alert auth-alert-error";
    alert.focus();
  };
  if (new URLSearchParams(location.search).has("expired"))
    report("Oturumun sona erdi. Lütfen yeniden giriş yap.");
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = form.querySelector("[type=submit]");
    const label = button.innerHTML;
    const email = form.elements.email.value.trim();
    const password = form.elements.password.value;
    if (
      form.dataset.auth === "register" &&
      password !== form.elements.passwordConfirm.value
    )
      return report("Şifreler birbiriyle eşleşmiyor.");
    alert.classList.add("hidden");
    button.disabled = true;
    button.textContent = "Lütfen bekle…";
    try {
      if (form.dataset.auth === "login") {
        await api.login(email, password);
        const onboarding = await api.getOnboarding();
        location.href = onboarding.completed ? "/today" : "/onboarding";
      } else {
        await api.register(
          form.elements.name.value.trim(),
          email,
          password,
          Intl.DateTimeFormat().resolvedOptions().timeZone || "Europe/Istanbul",
        );
        location.href = "/onboarding";
      }
    } catch (error) {
      report(error.message || "İşlem tamamlanamadı. Yeniden dene.");
    } finally {
      button.disabled = false;
      button.innerHTML = label;
    }
  });
});
