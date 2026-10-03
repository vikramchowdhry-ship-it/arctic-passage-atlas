/* Enquiry form without a server: it composes an email to the address in site-config.js and opens the
 * visitor's mail program. Nothing is sent to, or stored by, this website. */
(function () {
  "use strict";
  var cfg = window.ATLAS_SITE || {};


  /* The email the form composes. `d` is anything with a get(name) method, such as FormData. */
  function buildMessage(cfg, d) {
    var topic = d.get("topic"), org = (d.get("company") || "").trim(), name = (d.get("name") || "").trim();
    var subject = "[Arctic Passage Atlas] " + topic + (org ? " \u2014 " + org : "");
    var body = [
      "Name: " + name,
      "Organisation: " + org,
      "Reply-to email: " + (d.get("email") || "").trim(),
      "Topic: " + topic,
      "Timeframe: " + (d.get("timeframe") || "not stated"),
      "",
      (d.get("message") || "").trim(),
      "",
      "-- Sent from the enquiry form on the Arctic Passage Atlas website. --"
    ].join("\r\n");
    var href = "mailto:" + cfg.contactEmail + "?subject=" + encodeURIComponent(subject) + "&body=" + encodeURIComponent(body);
    return { subject: subject, body: body, href: href };
  }
  if (typeof module !== "undefined" && module.exports) module.exports = { buildMessage: buildMessage };

  function $(sel) { return document.querySelector(sel); }
  function setLink(id, href, text) {
    var el = document.getElementById(id);
    if (!el) return;
    if (href) { el.href = href; if (text) el.textContent = text; el.hidden = false; } else { el.hidden = true; }
  }

  document.addEventListener("DOMContentLoaded", function () {
    var form = $("#enquiry"), status = $("#enquiry-status");
    if (!form) return;
    setLink("link-email", cfg.contactEmail ? "mailto:" + cfg.contactEmail : "", cfg.contactEmail);
    setLink("link-linkedin", cfg.linkedinUrl, "LinkedIn");
    setLink("link-repo", cfg.repoUrl, "Source code");
    var note = $("#response-note");
    if (note) note.textContent = cfg.responseNote || "";
    var noAddress = !cfg.contactEmail;
    if (noAddress) {
      status.textContent = "Contact details are not set up yet, so the form is switched off. They are set in assets/site-config.js.";
      status.className = "form-status warn";
      form.querySelectorAll("input, select, textarea, button").forEach(function (el) { el.disabled = true; });
    }

    form.addEventListener("submit", function (ev) {
      ev.preventDefault();
      if (noAddress) return;
      var msg = buildMessage(cfg, new FormData(form)), subject = msg.subject, body = msg.body, href = msg.href;
      status.textContent = "Opening your email program with the message filled in. If nothing opens, copy it with the button below.";
      status.className = "form-status ok";
      $("#copy-enquiry").hidden = false;
      $("#copy-enquiry").onclick = function () {
        var text = "To: " + cfg.contactEmail + "\nSubject: " + subject + "\n\n" + body.replace(/\r\n/g, "\n");
        (navigator.clipboard ? navigator.clipboard.writeText(text) : Promise.reject()).then(function () {
          status.textContent = "Copied. Paste it into an email to " + cfg.contactEmail + ".";
        }).catch(function () { status.textContent = "Copy failed. Select the text in the form and copy it manually."; });
      };
      window.location.href = href;
    });
  });
})();
