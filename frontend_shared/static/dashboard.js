// Dashboard script for handling module selection and displaying tutors for the selected module
document.addEventListener("DOMContentLoaded", function () {
    const moduleButtons = document.querySelectorAll(".module-btn");
    const results = document.getElementById("tutor-results");
    const selectedModule = document.getElementById("selected-module");
    let activeRequest = 0;
    // Utility function to create an element with optional class and text content
    function element(tag, className, text) {
        const node = document.createElement(tag);
        node.className = className;
        if (text !== undefined) node.textContent = text;
        return node;
    }

    // Display a state message (loading, error, etc.) in the results container
    function showState(title, message, isError = false) {
        const state = element("div", `tutor-state${isError ? " tutor-state-error" : ""}`);
        state.append(
            element("h3", "", title),
            element("p", "", message)
        );
        results.replaceChildren(state);
    }

    // Badge showing the match percentage, coloured green (high), yellow (medium) or red (low)
    function matchBadge(similarity) {
        const tier = similarity >= 70 ? "high" : similarity >= 30 ? "medium" : "low";
        return element("span", `match-badge match-${tier}`, `${similarity}% match`);
    }

    // Create a card element for a tutor with their details and messaging option
    function tutorCard(tutor, moduleId) {
        const card = element("article", "tutor-card");
        const header = element("div", "tutor-card-header");
        const name = tutor.username || "Tutor";
        const avatar = element("div", "tutor-avatar", name.trim().charAt(0).toUpperCase() || "T");
        avatar.setAttribute("aria-hidden", "true");
        const identity = element("div", "tutor-identity");
        identity.append(element("h3", "tutor-name", name));
        header.append(avatar, identity);
        if (typeof tutor.similarity === "number") header.append(matchBadge(tutor.similarity));

        const preferences = element("div", "tutor-preferences");
        preferences.append(element("p", "preferences-label", "TEACHING PREFERENCES"));
        const chips = element("ul", "preference-list");
        const labels = {
            auditory: "Auditory",
            visual: "Visual",
            reading_writing: "Reading & writing",
            kinesthetic: "Kinesthetic"
        };
        Object.entries(tutor.teaching_preferences_completed === false ? {} : tutor.teaching_preferences || {}).forEach(([key, score]) => {
            const label = labels[key] || key.replace(/_/g, " ");
            chips.append(element("li", "preference-chip", `${label} \u00b7 ${score}/10`));
        });
        if (chips.childElementCount) {
            preferences.append(chips);
        } else {
            preferences.append(element("p", "preferences-empty", "Teaching preferences not set yet. Match unavailable."));
        }

        
        // trigger messaging (ppasses the userid and username)
        const message = element("button", "message-link", "Message tutor");
        message.type = "button";
        message.disabled = true;
        message.title = "Messaging is not available here yet";
        message.addEventListener("click", () => {
            window.location.href = `/api/dashboard/getmessages?user_id=${encodeURIComponent(tutor.id)}&username=${encodeURIComponent(tutor.username)}`;
        });
        message.disabled = false;
        message.title = "";

        const actions = element("div", "tutor-card-actions");
        actions.append(message, ...sessionControls(tutor, moduleId));
        card.append(header, preferences, actions);
        return card;
    }

    // Send a POST to the dashboard's sessions routes with the page's CSRF token
    async function postSession(path, body) {
        const response = await fetch(`/api/dashboard${path}`, {
            method: "POST",
            credentials: "same-origin",
            headers: { "Content-Type": "application/json", "X-CSRFToken": results.dataset.csrf },
            body: JSON.stringify(body || {})
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.error || `Request failed with status ${response.status}`);
        return data;
    }

    // Create, complete and cancel session buttons for testing reviews and payments
    function sessionControls(tutor, moduleId) {
        const create = element("button", "message-link", "Create session");
        const complete = element("button", "message-link", "Complete session");
        const cancel = element("button", "message-link", "Cancel session");
        const status = element("p", "session-status");
        status.setAttribute("role", "status");
        let session = null;

        [create, complete, cancel].forEach(button => { button.type = "button"; });

        function render() {
            const booked = session && session.status === "booked";
            create.disabled = booked;
            complete.disabled = !booked;
            cancel.disabled = !booked;
            status.textContent = session ? `Session ${session.status}` : "";
        }

        async function run(button, path, body) {
            button.disabled = true;
            try {
                session = await postSession(path, body);
            } catch (error) {
                status.textContent = error.message;
                console.error("Session request failed:", error);
                return;
            }
            render();
        }

        create.addEventListener("click", () =>
            run(create, "/sessions", { tutor_id: tutor.id, module_id: moduleId }));
        complete.addEventListener("click", () =>
            run(complete, `/sessions/${encodeURIComponent(session.id)}/complete`));
        cancel.addEventListener("click", () =>
            run(cancel, `/sessions/${encodeURIComponent(session.id)}/cancel`));

        render();
        return [create, complete, cancel, status];
    }

    // Add event listeners to module buttons to fetch and display tutors for the selected module
    moduleButtons.forEach(button => {
        button.addEventListener("click", async function () {
            const requestId = ++activeRequest;
            moduleButtons.forEach(item => item.setAttribute("aria-pressed", String(item === button)));
            selectedModule.textContent = button.querySelector(".module-name").textContent.trim();
            results.setAttribute("aria-busy", "true");
            showState("Finding tutors", "Loading available tutors for this module.");

            try {
                const response = await fetch(`/api/dashboard/get_tutors?module_id=${encodeURIComponent(button.dataset.module)}`);
                if (!response.ok || response.redirected) {
                    throw new Error(`Request failed with status ${response.status}`);
                }
                const { tutors } = await response.json();
                if (!Array.isArray(tutors)) throw new Error("Invalid tutor response");
                if (requestId !== activeRequest) return;
                if (tutors.length === 0) {
                    showState("No tutors found", "There are no tutors available for this module yet.");
                } else {
                    const grid = element("div", "tutor-grid");
                    tutors.forEach(tutor => grid.append(tutorCard(tutor, button.dataset.module)));
                    results.replaceChildren(grid);
                }
            } catch (error) {
                if (requestId !== activeRequest) return;
                showState("Couldn't load tutors", "Please try selecting this module again.", true);
                console.error("Error fetching tutors:", error);
            } finally {
                if (requestId === activeRequest) results.setAttribute("aria-busy", "false");
            }
        });
    });

    
    
});
