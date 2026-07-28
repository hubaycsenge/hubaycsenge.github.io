/* Client-side filtering for the wiki browsers (homepage panel + wiki index).
   Everything is already in the DOM, so this works offline and without fetch. */
(function () {
  "use strict";

  function setupBrowser(root) {
    var input = root.querySelector("[data-search-input]");
    var hits = root.querySelector("[data-hits]");
    var none = root.querySelector("[data-noresults]");
    var chips = Array.prototype.slice.call(root.querySelectorAll(".chip"));
    var cards = Array.prototype.slice.call(root.querySelectorAll(".card"));
    var blocks = Array.prototype.slice.call(root.querySelectorAll(".catblock"));
    var status = "all";
    var fulltext = null; // slug -> page text, loaded on first keystroke
    var loading = false;

    /* Cards carry title/summary/tags inline. The full page text is a separate
       fetch so the HTML stays small; until it lands (or if it never does, e.g.
       opened from a file:// URL) search still works over the inline metadata. */
    function loadFulltext() {
      if (fulltext || loading) return;
      loading = true;
      var url = root.getAttribute("data-index");
      if (!url || !window.fetch) return;
      fetch(url)
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (data) {
          if (!data) return;
          fulltext = data;
          apply();
        })
        .catch(function () { /* metadata-only search remains available */ });
    }

    function apply() {
      var terms = (input && input.value ? input.value : "")
        .toLowerCase()
        .split(/\s+/)
        .filter(Boolean);
      var shown = 0;

      cards.forEach(function (card) {
        var hay = card.getAttribute("data-search") || "";
        if (fulltext) hay += " " + (fulltext[card.getAttribute("data-slug")] || "");
        var okStatus = status === "all" || card.getAttribute("data-status") === status;
        var okTerms = terms.every(function (t) {
          return hay.indexOf(t) !== -1;
        });
        var visible = okStatus && okTerms;
        card.hidden = !visible;
        if (visible) shown++;
      });

      blocks.forEach(function (block) {
        var any = Array.prototype.some.call(block.querySelectorAll(".card"), function (c) {
          return !c.hidden;
        });
        block.hidden = !any;
      });

      if (none) none.hidden = shown !== 0;
      if (hits) {
        var filtering = terms.length || status !== "all";
        hits.textContent = filtering
          ? shown + (shown === 1 ? " page matches" : " pages match")
          : "";
      }
    }

    if (input) {
      input.addEventListener("focus", loadFulltext, { once: true });
      input.addEventListener("input", function () { loadFulltext(); apply(); });
      input.addEventListener("search", apply);
      input.addEventListener("keydown", function (e) {
        if (e.key === "Escape") {
          input.value = "";
          apply();
        }
      });
    }

    chips.forEach(function (chip) {
      chip.addEventListener("click", function () {
        status = chip.getAttribute("data-filter") || "all";
        chips.forEach(function (c) {
          c.classList.toggle("on", c === chip);
          c.setAttribute("aria-pressed", String(c === chip));
        });
        apply();
      });
      chip.setAttribute("aria-pressed", String(chip.classList.contains("on")));
    });

    apply();
  }

  Array.prototype.forEach.call(document.querySelectorAll("[data-browser]"), setupBrowser);

  /* Deep link: /#wikillm opens the panel and scrolls to it. */
  var field = document.getElementById("wikillm");
  if (field) {
    if (location.hash === "#wikillm") field.open = true;
    field.addEventListener("toggle", function () {
      if (field.open) {
        var q = field.querySelector("[data-search-input]");
        if (q && window.matchMedia("(min-width: 700px)").matches) q.focus();
      }
    });
  }
})();
