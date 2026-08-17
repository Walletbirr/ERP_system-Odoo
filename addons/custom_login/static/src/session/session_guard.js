/**
 * If the webclient is restored from the Back/Forward cache after logout
 * (or the session is otherwise dead), skip the "Odoo Session Expired"
 * dialog and send the user straight to the login page.
 *
 * Loaded only in the authenticated backend bundle so it never affects
 * the public login page itself.
 */
(function () {
    "use strict";

    function goToLogin() {
        try {
            window.location.replace(
                window.location.origin + "/web/login"
            );
        } catch (e) {
            window.location.href = "/web/login";
        }
    }

    // Restored from bfcache after logout → go to login immediately
    window.addEventListener("pageshow", function (e) {
        if (e.persisted) {
            goToLogin();
        }
    });

    // Odoo fires a custom event / shows a dialog on session expiry.
    // Catch the common RPC error path as early as we can.
    document.addEventListener(
        "DOMContentLoaded",
        function () {
            // If the page is the session-expired shell, redirect at once
            var bodyText = (document.body && document.body.innerText) || "";
            if (
                /session expired/i.test(bodyText) ||
                /odoo session expired/i.test(bodyText)
            ) {
                goToLogin();
            }
        },
        { once: true }
    );
})();
