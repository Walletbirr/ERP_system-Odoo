/**
 * theme_shell/static/src/core/browser/router_patch.js
 * ================================================================
 * Makes the webclient build/recognize "/binget" URLs instead of "/odoo",
 * WITHOUT forking web/static/src/core/browser/router.js.
 *
 * WHY NOT A FULL-FILE REPLACE (what the previous version of this file did):
 * Odoo names every transpiled JS module after the addon that physically
 * serves it: a file at web/static/src/core/browser/router.js becomes
 * "@web/core/browser/router"; the exact same file served from
 * theme_shell/static/src/... becomes "@theme_shell/core/browser/router"
 * instead. The manifest's "replace" directive only swaps which file
 * occupies a slot in the asset *bundle* — it does not rename that module
 * identity. So a full-file "replace" of router.js silently deletes the
 * "@web/core/browser/router" module from existence, and every one of the
 * ~100+ core files that `import ... from "@web/core/browser/router"` by
 * that exact name fails to load — which is the white screen / "needed by
 * other modules but not defined" error this file replaces the fix for.
 *
 * THIS APPROACH INSTEAD:
 * Leaves Odoo's real router.js completely untouched (still registered as
 * "@web/core/browser/router", so every core import keeps resolving), and
 * patches the two functions stock Odoo explicitly designed to be
 * patchable — see the comment directly on `router` in the real file:
 * "state <-> url conversions can be patched if needed in a custom
 * webclient." `router.stateToUrl` / `router.urlToState` are plain
 * properties on an exported object, not local function bindings, so
 * reassigning them here changes what every caller sees everywhere in the
 * app (they all call `router.stateToUrl(...)`, not the bare function).
 * We delegate to the ORIGINAL stateToUrl/urlToState for all the actual
 * parsing/building logic and only translate the "/odoo" <-> "/binget"
 * prefix, so any future Odoo core changes to route parsing are picked up
 * automatically — nothing here goes stale on upgrade.
 *
 * ONE THING PATCHING CANNOT FIX: router.js calls `startRouter()` at
 * import time, which runs before this file's patch has had a chance to
 * apply. So the very first parse of the page's URL (e.g. a hard refresh
 * or a typed-in address landing directly on /binget/...) happens through
 * the ORIGINAL, un-patched urlToState, which doesn't know "/binget" is a
 * valid prefix. We correct that once, right below, by re-parsing the
 * current URL with our patched urlToState and pushing the corrected
 * state in — this runs synchronously while JS modules are still being
 * evaluated, well before the webclient actually mounts and reads
 * `router.current`, so there's no visible flash of the wrong screen.
 *
 * KNOWN TRADE-OFF: clicking a sidebar link still triggers Odoo's own
 * click-interception listener inside router.js, which checks for a
 * hardcoded "/odoo" prefix and won't recognize "/binget" hrefs. That
 * listener's ONLY job is to upgrade what would otherwise be a normal link
 * click into a fast client-side transition (no full reload) — it isn't
 * required for the link to work. So /binget links still navigate
 * correctly, just via a full page reload instead of an instant SPA
 * transition. If that's worth fixing, it's a small addition (a capture-
 * phase click listener here that beats Odoo's to the punch) — say the
 * word and I'll add it.
 *
 * A related case of that same trade-off: Odoo's own module-upgrade flow
 * (Apps > Upgrade) finishes by doing its own hardcoded full-page
 * navigation back to "/odoo" once the upgrade completes server-side —
 * not a call through router.pushState/replaceState, so our patched
 * stateToUrl above never gets a chance to translate it. The browser
 * genuinely lands on a fresh "/odoo" page load, same as a hard refresh
 * would. The self-correction below now handles that direction too (see
 * below), by re-parsing the current URL and pushing the corrected state
 * back through OUR stateToUrl — which always prefers "/binget" — so the
 * address bar is corrected before the webclient mounts, same as the
 * /binget hard-refresh case.
 */
import { router, stateToUrl as originalStateToUrl, urlToState as originalUrlToState } from "@web/core/browser/router";
import { browser } from "@web/core/browser/browser";

function stateToUrl(state) {
    const url = originalStateToUrl(state);
    if (url === "/odoo" || url.startsWith("/odoo/") || url.startsWith("/odoo?")) {
        return "/binget" + url.slice(5);
    }
    return url;
}

function urlToState(urlObj) {
    if (urlObj.pathname === "/binget" || urlObj.pathname.startsWith("/binget/")) {
        const rewritten = new URL(urlObj.href);
        rewritten.pathname = "/odoo" + urlObj.pathname.slice("/binget".length);
        return originalUrlToState(rewritten);
    }
    return originalUrlToState(urlObj);
}

router.stateToUrl = stateToUrl;
router.urlToState = urlToState;

// Fix up the very first parse (see header comment above) when the page
// was loaded directly on a /binget/... URL (a hard refresh or typed-in
// address), OR directly on a bare /odoo/... URL (Odoo's own post-upgrade
// reload, or an old bookmark/link). Both funnel through the same fix:
// re-parse the current URL into a state object (urlToState doesn't care
// which prefix it came from — it's just the semantic route), then push
// that state back through router.replaceState, which rebuilds the
// address bar via OUR patched stateToUrl above — and that always prefers
// "/binget" regardless of which prefix we started from. This runs
// synchronously while JS modules are still being evaluated, well before
// the webclient actually mounts and reads router.current, so there's no
// visible flash of the wrong screen or wrong URL.
const path = browser.location.pathname;
const landedOnAlias =
    path === "/binget" || path.startsWith("/binget/") ||
    path === "/odoo" || path.startsWith("/odoo/");
if (landedOnAlias) {
    const correctedState = urlToState(new URL(browser.location.href));
    router.replaceState(correctedState, { replace: true, sync: true });
}
