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
  const button = form.querySelector('button[type="submit"]');
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
    if (form.dataset.accountType) data.account_type = form.dataset.accountType;
    if (form.elements.username) data.username = form.elements.username.value.trim();
    if (form.elements.college_id && form.elements.college_id.value) {
      data.college_id = form.elements.college_id.value;
    }
    try {
      const result = await submitToAPI(base, endpoint, data);
      if (id === "signup-form") sessionStorage.setItem("verificationEmail", data.email);
      form.reset();
      if (id === "login-form" && result.user.roles.includes("college_admin") && !result.user.college_id) {
        window.location.assign("/register-college");
      } else {
        window.location.assign(destination);
      }
    } catch (error) {
      showStatus(errorMessage(error), true);
    } finally {
      button.disabled = false;
      form.removeAttribute("aria-busy");
    }
  });
}

async function loadColleges() {
  const select = document.getElementById("college");
  const help = document.getElementById("college-help");
  const retry = document.getElementById("retry-colleges");
  select.disabled = true;
  select.setAttribute("aria-busy", "true");
  retry.hidden = true;
  const submit = document.querySelector('#signup-form button[type="submit"]');
  submit.disabled = true;
  help.textContent = "Loading available colleges…";
  try {
    const { colleges } = await requestJSON("/api/colleges/college");
    if (!Array.isArray(colleges)) throw new Error("Unable to load colleges. Please try again.");
    const options = [new Option("Select your college", "")];
    for (const college of colleges) {
      const option = new Option(college.domain ? `${college.name} (${college.domain})` : `${college.name} (email domain not configured)`, college.id);
      option.disabled = !college.domain;
      options.push(option);
    }
    select.replaceChildren(...options);
    const available = colleges.some(college => college.domain);
    select.disabled = !available;
    submit.disabled = !available;
    help.textContent = available ? "Select your college and use an email matching its student domain." : "No colleges are available for student signup yet. A college administrator must register one first.";
  } catch (error) {
    select.replaceChildren(new Option("Colleges unavailable", ""));
    help.textContent = `${errorMessage(error)} Please retry before signing up.`;
    retry.hidden = false;
  } finally {
    select.removeAttribute("aria-busy");
  }
}

async function loadAccount() {
  try {
    const { user } = await requestJSON("/api/users/users/me");
    document.getElementById("account-username").textContent = user.username;
    document.getElementById("account-email").textContent = user.email;
    statusElement.hidden = true;
    document.getElementById("account-details").hidden = false;
    if ((user.roles || []).includes("college_admin") && user.college_id) {
      setupLMSImport(user.college_id);
    }
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

async function setupLMSImport(collegeId) {
  document.getElementById("lms-settings").hidden = false;
  const form = document.getElementById("lms-form");
  const status = document.getElementById("lms-status");
  const saveButton = form.querySelector("button[type=submit]");
  const syncButton = document.getElementById("lms-sync-button");
  const moodleSettings = document.getElementById("moodle-settings");
  const providerHelp = document.getElementById("lms-provider-help");
  const base = `/api/lms/college/${encodeURIComponent(collegeId)}/lms`;
  let saved = false;
  let enabled = false;
  let sessionExpired = false;
  function selectProvider() {
    const provider = form.elements.provider.value;
    moodleSettings.hidden = provider !== "moodle";
    moodleSettings.disabled = provider !== "moodle";
    providerHelp.hidden = !provider || provider === "moodle";
    if (provider !== "moodle") {
      form.elements.api_key.value = "";
      status.textContent = "";
    }
  }
  form.elements.provider.addEventListener("change", selectProvider);
  selectProvider();
  async function call(path, method = "GET", data) {
    try {
      const { csrf_token } = await requestJSON("/api/users/auth/csrf");
      return await requestJSON(base + path, {
        method, headers: { "Content-Type": "application/json", "X-CSRFToken": csrf_token },
        ...(data === undefined ? {} : { body: JSON.stringify(data) }),
      });
    } catch (error) {
      if (error.status === 401) {
        sessionExpired = true;
        saveButton.disabled = syncButton.disabled = true;
        form.elements.api_key.value = "";
        error.message = "Your session has expired. Sign in again to manage your Moodle connection.";
        window.location.replace("/login");
      }
      throw error;
    }
  }
  function display(connection) {
    saved = Boolean(connection);
    enabled = Boolean(connection && connection.enabled);
    syncButton.disabled = !enabled;
    if (!connection) {
      status.textContent = "No college system connected yet.";
      return;
    }
    form.elements.provider.value = connection.provider;
    selectProvider();
    form.elements.base_url.value = connection.base_url;
    form.elements.enabled.checked = connection.enabled;
    const schedule = connection.enabled
      ? `Next sync: ${new Date(connection.next_sync_at).toLocaleString("en-IE", { timeZone: connection.timezone })} (${connection.timezone}).`
      : "Nightly synchronization is paused.";
    const last = connection.last_success_at
      ? `Last successful sync: ${new Date(connection.last_success_at).toLocaleString("en-IE", { timeZone: connection.timezone })}.`
      : "Awaiting first successful sync.";
    const counts = connection.counts
      ? `${connection.counts.users} users, ${connection.counts.courses} programmes, ${connection.counts.modules} modules.` : "";
    status.textContent = [schedule, last, counts, connection.last_error].filter(Boolean).join(" ");
  }
  try {
    display((await call("/connection")).connection);
  } catch (error) {
    status.textContent = errorMessage(error);
  }
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (form.elements.provider.value !== "moodle" || saveButton.disabled || !form.reportValidity()) return;
    saveButton.disabled = syncButton.disabled = true;
    const data = { provider: form.elements.provider.value, base_url: form.elements.base_url.value.trim(),
      api_key: form.elements.api_key.value, enabled: form.elements.enabled.checked, mapping: "academic" };
    form.elements.api_key.value = "";
    status.textContent = "Saving connection…";
    try {
      display((await call("/connection", "PUT", data)).connection);
    } catch (error) {
      status.textContent = errorMessage(error);
    } finally {
      saveButton.disabled = sessionExpired;
      syncButton.disabled = sessionExpired || !saved || !enabled;
    }
  });
  syncButton.addEventListener("click", async () => {
    if (syncButton.disabled) return;
    saveButton.disabled = syncButton.disabled = true;
    status.textContent = "Synchronizing college data…";
    try {
      display((await call("/sync", "POST", {})).connection);
    } catch (error) {
      status.textContent = errorMessage(error);
    } finally {
      saveButton.disabled = sessionExpired;
      syncButton.disabled = sessionExpired || !saved || !enabled;
    }
  });
}

switch (document.body.dataset.page) {
  case "login":
    setupForm("login-form", "/api/users", "/auth/login", "/account");
    if (new URLSearchParams(window.location.search).get("verified") === "1") {
      showStatus("Email verified. Sign in to continue.");
    }
    break;
  case "signup":
    setupForm("signup-form", "/api/registration", "/auth/signup", "/check-email");
    if (document.getElementById("college")) {
      document.getElementById("retry-colleges").addEventListener("click", loadColleges);
      loadColleges();
    }
    break;
  case "check-email":
    setupResend();
    break;
  case "verify-email":
    setupVerification();
    break;
  case "register-college":
    setupCollegeRegistration();
    break;
  case "account":
    loadAccount();
    break;
}


function setupResend() {
  const form = document.getElementById("resend-form");
  form.elements.email.value = sessionStorage.getItem("verificationEmail") || "";
  form.addEventListener("submit", async event => {
    event.preventDefault();
    const button = form.querySelector('button[type="submit"]');
    if (button.disabled || !form.reportValidity()) return;
    button.disabled = true;
    try {
      const result = await submitToAPI("/api/registration", "/auth/resend-verification", { email: form.elements.email.value.trim() });
      showStatus(result.message);
    } catch (error) { showStatus(errorMessage(error), true); }
    finally { button.disabled = false; }
  });
}

function setupVerification() {
  const token = new URLSearchParams(window.location.hash.slice(1)).get("token");
  history.replaceState(null, "", "/verify-email");
  const button = document.getElementById("verify-email-button");
  if (!token) { button.disabled = true; showStatus("Open the verification link from your email.", true); return; }
  button.addEventListener("click", async () => {
    if (button.disabled) return;
    button.disabled = true;
    try {
      await submitToAPI("/api/registration", "/auth/verify-email", { token });
      sessionStorage.removeItem("verificationEmail");
      window.location.replace("/login?verified=1");
    } catch (error) { showStatus(errorMessage(error), true); button.disabled = false; }
  });
}

async function setupCollegeRegistration() {
  const form = document.getElementById("college-form");
  try {
    const { user } = await requestJSON("/api/users/users/me");
    if (!user.roles.includes("college_admin")) { window.location.replace("/account"); return; }
    if (user.college_id) { window.location.replace("/account"); return; }
    statusElement.hidden = true;
    form.hidden = false;
  } catch (error) {
    if (error.status === 401) window.location.replace("/login");
    else showStatus(errorMessage(error), true);
    return;
  }
  form.addEventListener("submit", async event => {
    event.preventDefault();
    const button = form.querySelector('button[type="submit"]');
    if (button.disabled || !form.reportValidity()) return;
    button.disabled = true;
    try {
      const { csrf_token } = await requestJSON("/api/users/auth/csrf");
      await requestJSON("/api/colleges/college", {
        method: "POST", headers: { "Content-Type": "application/json", "X-CSRFToken": csrf_token },
        body: JSON.stringify({ name: form.elements.name.value.trim(), domain: form.elements.domain.value.trim() })
      });
      window.location.assign("/account");
    } catch (error) { showStatus(errorMessage(error), true); }
    finally { button.disabled = false; }
  });
}
