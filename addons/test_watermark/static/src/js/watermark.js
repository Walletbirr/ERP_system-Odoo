/** Test/UAT Watermark
 * Fetches the watermark configuration and injects a repeating,
 * click-through, fixed-position watermark overlay across the page.
 * Works on both backend (assets_backend) and website/portal (assets_frontend).
 */
(function () {
    "use strict";

    var STYLE_ID = "test_watermark_style";

    function escapeXml(str) {
        return String(str).replace(/[<>&'"]/g, function (c) {
            switch (c) {
                case "<": return "&lt;";
                case ">": return "&gt;";
                case "&": return "&amp;";
                case "'": return "&apos;";
                case '"': return "&quot;";
            }
        });
    }

    function buildSvgDataUri(text, color) {
        var safeText = escapeXml(text || "TEST");
        var safeColor = escapeXml(color || "#FF0000");
        var svg =
            '<svg xmlns="http://www.w3.org/2000/svg" width="420" height="260">' +
            '<text x="10" y="160" font-size="36" font-family="Arial, Helvetica, sans-serif" ' +
            'font-weight="bold" fill="' + safeColor + '" ' +
            'transform="rotate(-30 210,130)">' + safeText + "</text>" +
            "</svg>";
        return "data:image/svg+xml," + encodeURIComponent(svg);
    }

    function injectWatermark(config) {
        if (!config || !config.enabled) {
            return;
        }
        if (document.getElementById(STYLE_ID)) {
            return; // already injected
        }
        var opacity = config.opacity;
        if (opacity === undefined || opacity === null || isNaN(opacity)) {
            opacity = 0.12;
        }
        var dataUri = buildSvgDataUri(config.text, config.color);

        var style = document.createElement("style");
        style.id = STYLE_ID;
        style.type = "text/css";
        style.appendChild(document.createTextNode(
            "html.test_watermark_active::after," +
            "body.test_watermark_active::after {" +
            "content: '';" +
            "position: fixed;" +
            "top: 0; left: 0; right: 0; bottom: 0;" +
            "pointer-events: none;" +
            "z-index: 100000;" +
            "opacity: " + opacity + ";" +
            "background-image: url(\"" + dataUri + "\");" +
            "background-repeat: repeat;" +
            "}"
        ));
        document.head.appendChild(style);
        document.documentElement.classList.add("test_watermark_active");
        document.body.classList.add("test_watermark_active");
    }

    function fetchConfigAndInject() {
        fetch("/test_watermark/get_config", { credentials: "same-origin" })
            .then(function (response) {
                if (!response.ok) {
                    throw new Error("watermark config fetch failed");
                }
                return response.json();
            })
            .then(injectWatermark)
            .catch(function () {
                /* fail silently, never break the app because of the watermark */
            });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", fetchConfigAndInject);
    } else {
        fetchConfigAndInject();
    }
})();
