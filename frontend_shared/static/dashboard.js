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

    // Create a card element for a tutor with their details and messaging option
    function tutorCard(tutor) {
        const card = element("article", "tutor-card");
        const header = element("div", "tutor-card-header");
        const name = tutor.username || "Tutor";
        const avatar = element("div", "tutor-avatar", name.trim().charAt(0).toUpperCase() || "T");
        avatar.setAttribute("aria-hidden", "true");
        const identity = element("div", "tutor-identity");
        identity.append(element("h3", "tutor-name", name));
        header.append(avatar, identity);

        const preferences = element("div", "tutor-preferences");
        preferences.append(element("p", "preferences-label", "LEARNING PREFERENCES"));
        const chips = element("ul", "preference-list");
        const labels = {
            auditory: "Auditory",
            visual: "Visual",
            reading_writing: "Reading & writing",
            kinesthetic: "Kinesthetic"
        };
        Object.entries(tutor.teaching_preferences || {}).forEach(([key, score]) => {
            const label = labels[key] || key.replace(/_/g, " ");
            chips.append(element("li", "preference-chip", `${label} \u00b7 ${score}/10`));
        });
        if (chips.childElementCount) {
            preferences.append(chips);
        } else {
            preferences.append(element("p", "preferences-empty", "No preferences available."));
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
        card.append(header, preferences, message);
        return card;
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
                    tutors.forEach(tutor => grid.append(tutorCard(tutor)));
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
