/** @odoo-module **/
// In-app viewer for the Payment Proof / Client ID files.
//
// The server renders every previewable file as
//   <a class="o_ab_preview" href="<inline url>" data-ab-kind="image|pdf" ...>
// (see sale.order.payment.proof._preview_anchor). A click opens the file in
// an overlay inside Odoo: nothing is downloaded and the accountant keeps
// the page they were on. Ctrl/Cmd-click (or a middle click) still opens the
// plain inline URL in a new tab. Pure DOM on purpose: it does not depend on
// any Odoo internals, and if anything fails the link just opens in a new tab.

function el(tag, styles, text) {
    const node = document.createElement(tag);
    Object.assign(node.style, styles || {});
    if (text) {
        node.textContent = text;
    }
    return node;
}

function closeViewer() {
    const existing = document.querySelector(".o_ab_viewer");
    if (existing) {
        existing.remove();
    }
    document.removeEventListener("keydown", onKeydown, true);
}

function onKeydown(ev) {
    if (ev.key === "Escape") {
        ev.stopPropagation();
        closeViewer();
    }
}

function openViewer(anchor) {
    closeViewer();
    const url = anchor.getAttribute("href");
    const kind = anchor.dataset.abKind;
    const title = anchor.dataset.abTitle || "";
    const downloadUrl = anchor.dataset.abDownload || url;

    const overlay = el("div", {
        position: "fixed", inset: "0", zIndex: "10000",
        background: "rgba(0, 0, 0, 0.82)", display: "flex",
        flexDirection: "column",
    });
    overlay.className = "o_ab_viewer";

    const bar = el("div", {
        display: "flex", alignItems: "center", gap: "12px",
        padding: "10px 16px", color: "#fff",
    });
    const name = el("div", {
        flex: "1", overflow: "hidden", textOverflow: "ellipsis",
        whiteSpace: "nowrap", fontWeight: "600",
    }, title);
    const download = el("a", {
        color: "#fff", border: "1px solid rgba(255,255,255,.6)",
        borderRadius: "4px", padding: "4px 12px", textDecoration: "none",
    }, "Download");
    download.href = downloadUrl;
    download.target = "_blank";
    const close = el("button", {
        background: "transparent", border: "0", color: "#fff",
        fontSize: "28px", lineHeight: "1", cursor: "pointer",
    }, "\u00d7");
    close.type = "button";
    close.title = "Close (Esc)";
    close.addEventListener("click", closeViewer);
    bar.append(name, download, close);

    const body = el("div", {
        flex: "1", minHeight: "0", display: "flex",
        alignItems: "center", justifyContent: "center",
        overflow: "auto", padding: "0 16px 16px",
    });
    if (kind === "pdf") {
        const frame = el("iframe", {
            width: "100%", height: "100%", border: "0", background: "#fff",
        });
        frame.src = url;
        body.append(frame);
    } else {
        const img = el("img", {
            maxWidth: "100%", maxHeight: "100%", objectFit: "contain",
            cursor: "zoom-in", background: "#fff",
        });
        img.src = url;
        img.alt = title;
        let zoomed = false;
        img.addEventListener("click", () => {
            zoomed = !zoomed;
            img.style.maxWidth = zoomed ? "none" : "100%";
            img.style.maxHeight = zoomed ? "none" : "100%";
            img.style.cursor = zoomed ? "zoom-out" : "zoom-in";
            body.style.alignItems = zoomed ? "flex-start" : "center";
            body.style.justifyContent = zoomed ? "flex-start" : "center";
        });
        body.append(img);
    }
    // Click on the dark area around the file closes the viewer.
    body.addEventListener("click", (ev) => {
        if (ev.target === body) {
            closeViewer();
        }
    });

    overlay.append(bar, body);
    document.body.append(overlay);
    document.addEventListener("keydown", onKeydown, true);
}

// Capture phase: runs before the list row / form handlers, so a click on
// the eye never opens the record underneath.
document.addEventListener("click", (ev) => {
    const anchor = ev.target.closest && ev.target.closest("a.o_ab_preview");
    if (!anchor || ev.button !== 0 || ev.ctrlKey || ev.metaKey || ev.shiftKey) {
        return;
    }
    ev.preventDefault();
    ev.stopPropagation();
    try {
        openViewer(anchor);
    } catch (error) {
        console.warn("Preview failed, opening in a new tab", error);
        window.open(anchor.getAttribute("href"), "_blank");
    }
}, true);
