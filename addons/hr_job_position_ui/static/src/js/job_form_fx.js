/** @odoo-module **/

/**
 * Purely cosmetic, non-invasive enhancements for the redesigned
 * Job Position form:
 *   1. Auto-prepends a Font Awesome icon to each notebook tab based on
 *      its label text (Recruitment, Job Summary, Careers Portal,
 *      Compensation, ...).
 *   2. Adds a lightweight material-style ripple effect to buttons.
 *
 * No Odoo core component is patched: we simply watch the DOM for the
 * ".o_stunning_job_form" root (added by our view inheritance) and
 * decorate it once it appears. This keeps the module resilient to
 * unrelated customizations of the hr.job form.
 */

const TAB_ICONS = {
    "recruitment": "fa-user-plus",
    "job summary": "fa-file-text-o",
    "careers portal": "fa-globe",
    "compensation": "fa-money",
    "environment": "fa-map-marker",
};

function decorateTabs(root) {
    const notebook = root.querySelector(".o_stunning_notebook");
    if (!notebook || notebook.dataset.stunningTabsDone) {
        return;
    }
    const links = notebook.querySelectorAll(".nav-link");
    links.forEach((link) => {
        const label = link.textContent.trim().toLowerCase();
        const icon = TAB_ICONS[label];
        if (icon && !link.querySelector(".stunning-tab-icon")) {
            const i = document.createElement("i");
            i.className = `fa ${icon} stunning-tab-icon me-1`;
            link.prepend(i);
        }
    });
    notebook.dataset.stunningTabsDone = "1";
}

function onButtonClick(ev) {
    const btn = ev.currentTarget;
    const rect = btn.getBoundingClientRect();
    const diameter = Math.max(rect.width, rect.height);
    const radius = diameter / 2;

    const circle = document.createElement("span");
    circle.className = "stunning-ripple";
    circle.style.width = circle.style.height = `${diameter}px`;
    circle.style.left = `${ev.clientX - rect.left - radius}px`;
    circle.style.top = `${ev.clientY - rect.top - radius}px`;

    const old = btn.querySelector(".stunning-ripple");
    if (old) {
        old.remove();
    }
    btn.appendChild(circle);
    setTimeout(() => circle.remove(), 600);
}

function bindRipples(root) {
    const form = root.querySelector(".o_stunning_job_form");
    if (!form || form.dataset.stunningRippleDone) {
        return;
    }
    form.querySelectorAll("button.btn").forEach((btn) => {
        btn.addEventListener("click", onButtonClick);
    });
    form.dataset.stunningRippleDone = "1";
}

function enhance() {
    try {
        const root = document.body;
        if (!root || !root.querySelector(".o_stunning_job_form")) {
            return;
        }
        decorateTabs(root);
        bindRipples(root);
    } catch (e) {
        console.error("[hr_job_position_ui] non-fatal enhance error:", e);
    }
}

function init() {
    // Defensive: never assume document.body already exists at the point
    // this script executes — depending on bundle load order this file
    // could run before the <body> tag has been parsed. Observing a null
    // target throws and, since this file is concatenated into a shared
    // bundle, would silently prevent the rest of the bundle (including
    // the Odoo webclient bootstrap) from running.
    if (!document.body) {
        document.addEventListener("DOMContentLoaded", init, { once: true });
        return;
    }
    try {
        const observer = new MutationObserver(() => enhance());
        observer.observe(document.body, { childList: true, subtree: true });
        enhance();
    } catch (e) {
        // Never let a cosmetic enhancement break the backend.
        console.error("[hr_job_position_ui] non-fatal init error:", e);
    }
}

init();
