"use strict";

const statusElement = document.getElementById("form-status");

function showStatus(message, error = false) {
  statusElement.textContent = message;
  statusElement.className = error ? "alert alert-danger" : "alert alert-info";
  statusElement.hidden = false;
  if (error) statusElement.focus();
}

async function requestJSON(url, options = {}) {
  const response = await fetch(url, { credentials: "same-origin", ...options });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(data.error || "The service is unavailable. Please try again.");
    error.status = response.status;
    throw error;
  }
  return data;
}

async function submitToAPI(base, path, data) {
  // Fetch from the receiving service: signup and login have different CSRF sessions.
  const { csrf_token } = await requestJSON(`${base}/auth/csrf`);
  if (!csrf_token) throw new Error("Unable to start a secure session. Please try again.");
  return requestJSON(`${base}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-CSRFToken": csrf_token },
    body: JSON.stringify(data),
  });
}

function errorMessage(error) {
  return error instanceof TypeError ? "Unable to connect. Check your connection and try again." : error.message;
}

function setupForm(id, base, endpoint, destination) {
  const form = document.getElementById(id);
  const button = form.querySelector("button");
  const password = form.elements.password;
  const confirmation = form.elements.confirm_password;
  if (confirmation) {
    const validate = () => confirmation.setCustomValidity(
      confirmation.value === password.value ? "" : "Passwords must match."
    );
    password.addEventListener("input", validate);
    confirmation.addEventListener("input", validate);
  }
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (button.disabled || !form.reportValidity()) return;
    button.disabled = true;
    form.setAttribute("aria-busy", "true");
    showStatus("Please wait…");
    const data = { email: form.elements.email.value.trim(), password: password.value };
    if (form.elements.username) data.username = form.elements.username.value.trim();
    try {
      await submitToAPI(base, endpoint, data);
      form.reset();
      window.location.assign(destination);
    } catch (error) {
      showStatus(errorMessage(error), true);
    } finally {
      button.disabled = false;
      form.removeAttribute("aria-busy");
    }
  });
}

async function loadAccount() {
  try {
    const { user } = await requestJSON("/api/users/users/me");
    document.getElementById("account-username").textContent = user.username;
    document.getElementById("account-email").textContent = user.email;
    statusElement.hidden = true;
    document.getElementById("account-details").hidden = false;
  } catch (error) {
    if (error.status === 401) window.location.replace("/login");
    else showStatus(errorMessage(error), true);
  }
  const button = document.getElementById("logout-button");
  button.addEventListener("click", async () => {
    button.disabled = true;
    try {
      await submitToAPI("/api/users", "/auth/logout", {});
      window.location.replace("/login");
    } catch (error) {
      if (error.status === 401) window.location.replace("/login");
      else showStatus(errorMessage(error), true);
      button.disabled = false;
    }
  });
}

switch (document.body.dataset.page) {
  case "login":
    setupForm("login-form", "/api/users", "/auth/login", "/account");
    if (new URLSearchParams(window.location.search).get("registered") === "1") {
      showStatus("Account created. Sign in to get started.");
    }
    break;
  case "signup":
    setupForm("signup-form", "/api/registration", "/auth/signup", "/login?registered=1");
    break;
  case "account":
    loadAccount();
    break;
}
