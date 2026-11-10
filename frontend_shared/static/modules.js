"use strict";

// Module names and application text are always inserted as text, never HTML.
async function moduleRequest(path, method = "GET", data) {
  const { csrf_token } = await requestJSON("/api/users/auth/csrf");
  return requestJSON("/api/lms" + path, {
    method,
    headers: { "Content-Type": "application/json", "X-CSRFToken": csrf_token },
    ...(data === undefined ? {} : { body: JSON.stringify(data) }),
  });
}

function moduleError(status, error) {
  if (error.status === 401) window.location.replace("/login");
  status.textContent = errorMessage(error);
}

function element(tag, text, className = "") {
  const item = document.createElement(tag);
  item.textContent = text;
  item.className = className;
  return item;
}

function setupProgrammeModules() {
  const form = document.getElementById("module-search-form");
  if (!form) return;
  const results = document.getElementById("programme-modules");
  const status = document.getElementById("module-search-status");
  const openButton = document.getElementById("open-tutor-applications");
  const panel = document.getElementById("tutor-application-panel");
  if (openButton && panel) {
    const heading = document.getElementById("student-dashboard-title");
    const intro = document.getElementById("student-dashboard-intro");
    const dashboardHeading = heading.textContent;
    const dashboardIntro = intro.textContent;
    function closeApplications() {
      heading.textContent = dashboardHeading;
      intro.textContent = dashboardIntro;
      panel.hidden = true;
      openButton.textContent = "Apply to be a tutor";
      openButton.setAttribute("aria-expanded", "false");
      openButton.focus();
    }
    openButton.addEventListener("click", () => {
      if (!panel.hidden) {
        closeApplications();
        return;
      }
      heading.textContent = "Apply to be a Tutor";
      intro.textContent = "Share your knowledge. Choose an eligible module below and apply to tutor students in earlier years of your programme.";
      panel.hidden = false;
      openButton.textContent = "Close the apply menu";
      openButton.setAttribute("aria-expanded", "true");
      document.getElementById("tutor-module-query").focus();
    });
    document.getElementById("close-tutor-applications").addEventListener("click", closeApplications);
  }
  let searchNumber = 0;
  async function search() {
    const number = ++searchNumber;
    status.textContent = "Loading programme modules…";
    try {
      const query = form.elements.q.value;
      const { modules } = await moduleRequest("/students/me/modules?q=" + encodeURIComponent(query));
      if (number !== searchNumber) return;
      results.replaceChildren();
      const eligibleModules = modules.filter(module => module.can_apply_to_tutor === true);
      if (openButton && !query) {
        openButton.hidden = !eligibleModules.some(module =>
          !module.application_status && !(module.roles || []).includes("tutor"));
      }
      for (const module of eligibleModules) {
        const item = element("li", "", "list-group-item p-3");
        item.append(element("h3", (module.display_name || module.name) + (module.code ? ` (${(module.display_code || module.code)})` : ""), "h6"));
        const roles = module.roles || [];
        if (roles.includes("student")) item.append(element("span", "Student", "badge text-bg-primary me-2"));
        if (roles.includes("tutor")) item.append(element("span", "Tutor", "badge text-bg-success me-2"));
        if (module.application_status) {
          item.append(element("p", "Tutor application: " + module.application_status, "mt-2 mb-0"));
        } else if (module.can_apply_to_tutor === true && !roles.includes("tutor")) {
          const application = document.createElement("form");
          application.className = "mt-3";
          const gradeId = "tutor-grade-" + module.id;
          const label = element("label", "What was your grade for this module? (0–100)", "form-label");
          label.htmlFor = gradeId;
          const grade = document.createElement("input");
          grade.id = gradeId;
          grade.type = "number";
          grade.min = "0";
          grade.max = "100";
          grade.step = "any";
          grade.required = true;
          grade.className = "form-control mb-2";
          const button = element("button", "Apply to be a tutor", "btn btn-outline-primary");
          button.type = "submit";
          const feedback = element("p", "", "mt-2 mb-0");
          feedback.setAttribute("role", "status");
          application.append(label, grade, button, feedback);
          application.addEventListener("submit", async event => {
            event.preventDefault();
            if (button.disabled || !application.reportValidity()) return;
            button.disabled = true;
            feedback.textContent = "Submitting application…";
            try {
              const { application: saved } = await moduleRequest(`/students/me/modules/${encodeURIComponent(module.id)}/tutor-application`, "POST", { grade: Number(grade.value) });
              feedback.textContent = "Tutor application: " + saved.status;
              grade.disabled = true;
              button.textContent = "Application submitted";
            } catch (error) {
              moduleError(feedback, error);
              button.disabled = false;
            }
          });
          item.append(application);
        }
        results.append(item);
      }
      status.textContent = eligibleModules.length ? `${eligibleModules.length} module(s) available to apply to tutor.` : "No eligible modules found. You can only apply to tutor modules from previous years of your programme.";
    } catch (error) {
      if (number === searchNumber) {
        results.replaceChildren();
        if (panel) panel.hidden = false;
        moduleError(status, error);
      }
    }
  }
  form.addEventListener("submit", event => { event.preventDefault(); search(); });
  search();
}

function setupTutorReviews() {
  const panel = document.getElementById("tutor-applications");
  if (!panel) return;
  const status = document.getElementById("tutor-review-status");
  const list = document.getElementById("tutor-review-list");
  const base = panel.dataset.reviewPath || `/college/${encodeURIComponent(panel.dataset.collegeId)}/tutor-applications`;
  async function load() {
    status.textContent = "Loading applications…";
    try {
      const { applications } = await moduleRequest(base);
      list.replaceChildren();
      for (const application of applications) {
        const item = element("li", "", "list-group-item p-3");
        item.append(element("h3", `${application.username} — ${application.module_name}`, "h6"));
        item.append(element("p", application.grade == null ? "Grade: not provided" : `Grade: ${application.grade}/100`));
        const feedback = element("p", "", "mt-2 mb-0");
        feedback.setAttribute("role", "status");
        const buttons = [];
        for (const [decision, label] of [["approved", "Approve"], ["rejected", "Reject"]]) {
          const button = element("button", label, "btn btn-outline-secondary me-2");
          button.type = "button";
          buttons.push(button);
          button.addEventListener("click", async () => {
            if (button.disabled) return;
            buttons.forEach(item => { item.disabled = true; });
            try {
              await moduleRequest(`${base}/${encodeURIComponent(application.id)}/review`, "POST", { decision });
              feedback.textContent = "Application " + decision + ".";
            } catch (error) {
              moduleError(feedback, error);
              buttons.forEach(item => { item.disabled = false; });
            }
          });
          item.append(button);
        }
        item.append(feedback);
        list.append(item);
      }
      status.textContent = applications.length ? `${applications.length} pending application(s).` : "No pending tutor applications.";
    } catch (error) { moduleError(status, error); }
  }
  document.getElementById("refresh-tutor-applications").addEventListener("click", load);
  load();
}

setupProgrammeModules();
setupTutorReviews();
