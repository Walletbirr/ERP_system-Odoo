/**
 * Standalone login-page enhancement — plain JS, not an Owl/Odoo module,
 * since this needs to run on the public /web/login page rather than
 * inside the authenticated backend webclient.
 *
 * WHY THIS APPROACH (read before touching this file):
 * The login page is the one place where breaking the template locks
 * everyone out. Rather than inheriting Odoo's actual `web.login` /
 * `web.login_layout` QWeb templates via xpath (which throws a hard
 * install/render error if the target markup doesn't match exactly),
 * this only:
 *   1. Finds the existing login form at runtime (never rewrites it).
 *   2. Wraps it and inserts a brand header above it.
 *   3. Hides a few links/fields via a CSS class — never removes them
 *      from the DOM, so nothing they'd submit (like the database
 *      field's value) is lost even while visually hidden.
 * If step 1 doesn't find what it expects, the script returns — the
 * stock Odoo login page keeps working exactly as it does today.
 *
 * VERIFY: ".oe_login_form" and "#wrapwrap" are my best-confidence,
 * long-stable Odoo selectors. The logo is now found generically as
 * "the first <img> inside the card" rather than by guessing a class
 * name — an earlier version guessed ".o_page_login_logo" and that
 * guess was wrong on this Odoo 18 build, which is why the logo never
 * moved into the new header and its original (now-orphaned) wrapper
 * div was left behind, showing as a stray line under the heading.
 * input[name="db"] / hrefs containing "reset_password",
 * "/web/database/manager", and "odoo.com" are Odoo's actual stable
 * route names, which is more reliable than guessing CSS class names.
 */
(function () {
    "use strict";

    if (!/\/web\/login\b/.test(window.location.pathname)) {
        return; // only ever runs on the login page itself
    }

    function hide(el) {
        if (el) {
            el.classList.add("o_custom_login_hidden");
        }
    }

    // Hides a link plus its wrapper if, after hiding the link, that
    // wrapper has nothing left in it but separator characters (e.g. the
    // "Manage Databases | Powered by Odoo" row collapsing to a stray "|"
    // once both links are hidden).
    function hideLinkAndEmptyParent(selector) {
        document.querySelectorAll(selector).forEach(function (a) {
            var parent = a.parentElement;
            hide(a);
            if (!parent) {
                return;
            }
            var remainingText = Array.prototype.slice
                .call(parent.childNodes)
                .filter(function (n) {
                    return n !== a;
                })
                .map(function (n) {
                    return n.textContent || "";
                })
                .join("")
                .replace(/[\s|/,•·-]/g, "");
            var hasOtherVisibleChildren = Array.prototype.slice
                .call(parent.children)
                .some(function (c) {
                    return c !== a && !c.classList.contains("o_custom_login_hidden");
                });
            if (!remainingText && !hasOtherVisibleChildren) {
                hide(parent);
            }
        });
    }

    // Turns one input + its <label> into a floating-label field: the
    // label sits inside the input area until it's focused or filled,
    // then animates up into a small caption (see login.scss). The
    // input itself is never rewritten — only wrapped and reordered
    // relative to its own label, which doesn't affect the label's
    // for/id association or accessibility.
    // `withToggle: true` additionally adds a show/hide button for a
    // password field — it only ever flips the input's type attribute
    // between "password" and "text"; the value the person already
    // typed is untouched and still submits normally either way.
    function setupFloatingField(input, iconClass, withToggle) {
        if (!input || input.closest(".o_custom_login_field")) {
            return;
        }
        var label = null;
        if (input.id) {
            label = document.querySelector('label[for="' + input.id + '"]');
        }
        if (!label && input.previousElementSibling && input.previousElementSibling.tagName === "LABEL") {
            label = input.previousElementSibling;
        }

        // Force the CSS :placeholder-shown trick to work reliably,
        // regardless of whether Odoo set its own placeholder text.
        input.setAttribute("placeholder", " ");

        var field = document.createElement("div");
        field.className = "o_custom_login_field";
        input.parentNode.insertBefore(field, input);
        field.appendChild(input);

        var icon = document.createElement("i");
        icon.className = "fa " + iconClass + " o_custom_login_field_icon";
        field.appendChild(icon);

        if (label) {
            // Moved to AFTER the input on purpose — that's what lets the
            // CSS use a sibling selector (input:focus ~ label) to animate
            // it, with no JS needed to track focus state.
            label.classList.add("o_custom_login_floating_label");
            field.appendChild(label);
        }

        if (withToggle) {
            field.classList.add("o_custom_login_has_toggle");
            var toggle = document.createElement("button");
            toggle.type = "button"; // critical: never "submit", or clicking it would submit the form
            toggle.className = "o_custom_login_toggle_visibility";
            toggle.setAttribute("aria-label", "Show password");
            var toggleIcon = document.createElement("i");
            toggleIcon.className = "fa fa-eye";
            toggle.appendChild(toggleIcon);
            toggle.addEventListener("click", function () {
                var showing = input.type === "text";
                input.type = showing ? "password" : "text";
                toggleIcon.className = "fa " + (showing ? "fa-eye" : "fa-eye-slash");
                toggle.setAttribute("aria-label", showing ? "Show password" : "Hide password");
            });
            field.appendChild(toggle);
        }
    }

    function init() {
        var wrap = document.getElementById("wrapwrap");
        var form = document.querySelector(".oe_login_form");
        if (!wrap || !form) {
            return; // selector guess didn't match — do nothing, stay stock
        }

        // Walk up from the form to the node that is a DIRECT child of
        // #wrapwrap — sidesteps guessing at Bootstrap wrapper class
        // names, and becomes our glass card.
        var stage = form;
        while (stage.parentElement && stage.parentElement !== wrap) {
            stage = stage.parentElement;
        }
        if (stage.parentElement !== wrap) {
            return; // unexpected structure — bail out safely rather than guess
        }

        wrap.classList.add("o_custom_login_bg");
        stage.classList.add("o_custom_login_stage");

        // ---- Brand header: logo + company name, prepended into the card ----
        var brand = document.createElement("div");
        brand.className = "o_custom_login_brand";

        var logoWrap = document.createElement("div");
        logoWrap.className = "o_custom_login_logo";

        // Find the logo generically — the first <img> anywhere in the
        // card — rather than guessing a specific class name. There's
        // only ever one image on this page (the company logo), so this
        // is more reliable than a class-name guess that can silently
        // miss on a given Odoo version.
        var logoImg = stage.querySelector("img");
        var originalLogoParent = logoImg ? logoImg.parentElement : null;
        if (logoImg) {
            logoWrap.appendChild(logoImg); // relocate the real node, don't duplicate it
            // Clean up whatever wrapper it used to sit in (that wrapper
            // likely had its own border/divider under it) now that it's
            // empty — otherwise it's left behind as a stray line.
            if (originalLogoParent && originalLogoParent !== logoWrap && !originalLogoParent.contains(form)) {
                hide(originalLogoParent);
            }
        }
        brand.appendChild(logoWrap);

        var textWrap = document.createElement("div");
        textWrap.className = "o_custom_login_brand_text";
        var heading = document.createElement("div");
        heading.className = "o_custom_login_heading";
        heading.textContent = "BINGET Holding Plc";
        var tagline = document.createElement("div");
        tagline.className = "o_custom_login_tagline";
        tagline.textContent = "Sign in to access your workspace";
        textWrap.appendChild(heading);
        textWrap.appendChild(tagline);
        brand.appendChild(textWrap);

        stage.insertBefore(brand, stage.firstChild);

        // ---- Hide the database selector, "Reset Password", "Manage
        // Databases", and "Powered by Odoo" — hidden via CSS class only,
        // never removed, so the db field's value still submits normally
        // even while invisible. ----
        var dbInput = document.querySelector('input[name="db"]');
        if (dbInput) {
            var dbContainer = dbInput.closest(".input-group") || dbInput.parentElement;
            hide(dbContainer);
            var prevLabel = dbContainer && dbContainer.previousElementSibling;
            if (prevLabel && /database/i.test(prevLabel.textContent || "")) {
                hide(prevLabel);
            }
        }
        hideLinkAndEmptyParent('a[href*="/web/database/manager"]');
        hideLinkAndEmptyParent('a[href*="reset_password"]');
        hideLinkAndEmptyParent('a[href*="odoo.com"]');

        // "Choose a user" is Odoo core's web.user_switch Owl component
        // (web/static/src/core/user_switch/), which portals a button into
        // the email field's <label> when the browser has a cached login
        // for this database. It's a separate component, not text sitting
        // inside our form, so it's hidden via its real class names
        // (.o_user_switch_btn / .o_user_switch) in login.scss instead —
        // that also covers the case where 2+ cached users make it hide
        // the real form entirely, which login.scss forces back visible.

        // ---- Floating-label email / password fields ----
        var loginInput = form.querySelector('input[name="login"]');
        var passwordInput = form.querySelector('input[name="password"]');
        setupFloatingField(loginInput, "fa-envelope", false);
        setupFloatingField(passwordInput, "fa-lock", true);

        // ---- Email-format validation (reject phone numbers / free text) ----
        // Odoo ships the login field as type="text" so phones & logins are
        // accepted. We keep type="text" for compatibility but enforce a
        // real email structure via pattern + a submit guard that shows a
        // compact, design-matching message instead of the browser's
        // native tooltip.
        if (loginInput) {
            loginInput.setAttribute(
                "pattern",
                "[^@\\s]+@[^@\\s]+\\.[^@\\s]+"
            );
            loginInput.setAttribute(
                "title",
                "Please enter a valid email address (e.g. name@company.com)"
            );
            // Clear any previous custom error when the user starts typing again.
            loginInput.addEventListener("input", function () {
                loginInput.setCustomValidity("");
                var existing = form.querySelector(".o_custom_login_client_error");
                if (existing) {
                    existing.remove();
                }
            });
        }

        function showClientError(message) {
            var existing = form.querySelector(".o_custom_login_client_error");
            if (existing) {
                existing.remove();
            }
            var err = document.createElement("div");
            err.className = "o_custom_login_client_error";
            err.setAttribute("role", "alert");
            err.textContent = message;
            // Place it just above the submit button so layout matches the
            // server-side "Wrong login/password" alert position.
            var submitBtn = form.querySelector(
                'button[type="submit"], input[type="submit"], .btn-primary'
            );
            if (submitBtn) {
                submitBtn.parentNode.insertBefore(err, submitBtn);
            } else {
                form.appendChild(err);
            }
        }

        form.addEventListener("submit", function (e) {
            if (!loginInput) {
                return;
            }
            var value = (loginInput.value || "").trim();
            // Simple, robust email check (same idea as the pattern attribute).
            var emailOk = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
            if (!emailOk) {
                e.preventDefault();
                e.stopPropagation();
                loginInput.setCustomValidity(
                    "Please enter a valid email address"
                );
                loginInput.reportValidity();
                showClientError("Please enter a valid email address");
                loginInput.focus();
                return false;
            }
            loginInput.setCustomValidity("");
        });

        // ---- Normalize Odoo's server-side error alert so it sits in the
        // same visual slot as our client error and does not force the
        // card to scroll. ----
        // Odoo typically injects <p class="alert alert-danger"> (or a
        // close relative) between the password field and the submit
        // button after a failed login. We just ensure it is visible and
        // leave the heavy lifting to the CSS rules in login.scss.
        var serverAlerts = stage.querySelectorAll(
            ".alert, .alert-danger, p[role='alert'], .o_error"
        );
        serverAlerts.forEach(function (el) {
            el.classList.add("o_custom_login_server_error");
        });

        // Everything Odoo renders after the submit button inside the
        // form (e.g. "Log in as superuser") and everything after the
        // form itself within the card (e.g. the old divider + "Manage
        // Databases | Powered by Odoo" footer) isn't part of this
        // redesign — hide it all rather than trying to guess every
        // individual element's markup.
        var submitBtn = form.querySelector(
            'button[type="submit"], input[type="submit"], .btn-primary'
        );
        if (submitBtn) {
            var afterBtn = submitBtn.nextElementSibling;
            while (afterBtn) {
                // Never hide the error alerts we just normalized.
                if (
                    afterBtn.classList.contains("o_custom_login_server_error") ||
                    afterBtn.classList.contains("o_custom_login_client_error") ||
                    afterBtn.classList.contains("alert")
                ) {
                    afterBtn = afterBtn.nextElementSibling;
                    continue;
                }
                hide(afterBtn);
                afterBtn = afterBtn.nextElementSibling;
            }
        }
        var afterForm = form.nextElementSibling;
        while (afterForm) {
            hide(afterForm);
            afterForm = afterForm.nextElementSibling;
        }
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
