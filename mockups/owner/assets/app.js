(function () {
  "use strict";

  var D = window.LEVIII_DATA;

  function initNav() {
    var page = document.body.getAttribute("data-page");
    document.querySelectorAll(".nav-pill__item").forEach(function (el) {
      if (el.getAttribute("data-nav") === page) {
        el.classList.add("is-active");
      }
    });
  }

  function openSheet(title, bodyHtml) {
    var overlay = document.getElementById("sheet-overlay");
    if (!overlay) return;
    overlay.querySelector(".sheet__title").textContent = title;
    overlay.querySelector(".sheet__body").innerHTML = bodyHtml;
    overlay.classList.add("is-open");
    overlay.setAttribute("aria-hidden", "false");
  }

  function closeSheet() {
    var overlay = document.getElementById("sheet-overlay");
    if (!overlay) return;
    overlay.classList.remove("is-open");
    overlay.setAttribute("aria-hidden", "true");
  }

  function initSheet() {
    var overlay = document.getElementById("sheet-overlay");
    if (!overlay) return;
    overlay.addEventListener("click", function (e) {
      if (e.target === overlay || e.target.closest("[data-sheet-close]")) {
        closeSheet();
      }
    });
    document.addEventListener("click", function (e) {
      var btn = e.target.closest("[data-why]");
      if (!btn) return;
      var title = btn.getAttribute("data-why-title") || "Why this number?";
      var body = btn.getAttribute("data-why-body") || "Example explanation for this mockup.";
      openSheet(title, "<p>" + body + "</p>");
    });
  }

  function bindData() {
    if (!D) return;
    document.querySelectorAll("[data-bind]").forEach(function (el) {
      var path = el.getAttribute("data-bind").split(".");
      var val = D;
      for (var i = 0; i < path.length; i++) {
        if (val == null) break;
        val = val[path[i]];
      }
      if (val == null) return;
      var fmt = el.getAttribute("data-format");
      if (fmt === "kes" && typeof val === "number") {
        el.textContent = D.formatKES(val);
      } else {
        el.textContent = val;
      }
    });
  }

  function initDismissCards() {
    document.addEventListener("click", function (e) {
      var btn = e.target.closest("[data-dismiss-card], [data-later-card]");
      if (!btn) return;
      var card = btn.closest(".card");
      if (card) card.classList.add("is-dismissed");
    });
  }

  function initMoneyPeriod() {
    var root = document.getElementById("money-root");
    if (!root || !D.money) return;
    var buttons = root.querySelectorAll(".segmented button");
    function render(period) {
      var p = D.money.periods[period];
      if (!p) return;
      var labels = { today: "What you kept today", week: "What you kept this week", month: "What you kept this month" };
      var heroLabel = root.querySelector("[data-money-hero-label]");
      if (heroLabel) heroLabel.textContent = labels[period] || labels.month;
      root.querySelector("[data-money-kept]").textContent = D.formatKES(p.kept);
      root.querySelector("[data-money-kept-of100]").textContent =
        "out of every KES 100 you sold, KES " + p.keptOf100 + " was kept";
      root.querySelector("[data-pl-sales]").textContent = p.sales.toLocaleString("en-KE");
      root.querySelector("[data-pl-ing]").textContent = p.ingredients.toLocaleString("en-KE");
      root.querySelector("[data-pl-ing-pct]").textContent = p.ingredientsPct + " of every 100";
      root.querySelector("[data-pl-left]").textContent = p.leftAfterIngredients.toLocaleString("en-KE");
      root.querySelector("[data-pl-wages]").textContent = p.wages.toLocaleString("en-KE");
      root.querySelector("[data-pl-wages-pct]").textContent = p.wagesPct + " of every 100";
      root.querySelector("[data-pl-run]").textContent = p.runningCosts.toLocaleString("en-KE");
      root.querySelector("[data-pl-run-pct]").textContent = p.runningCostsPct + " of every 100";
      root.querySelector("[data-pl-kept]").textContent = p.kept.toLocaleString("en-KE");
      root.querySelector("[data-breakeven-time]").textContent = p.breakEvenTime;
    }
    buttons.forEach(function (btn) {
      btn.addEventListener("click", function () {
        buttons.forEach(function (b) {
          b.classList.remove("is-active");
        });
        btn.classList.add("is-active");
        render(btn.getAttribute("data-period"));
      });
    });
    render("month");
  }

  function initStockApprove() {
    document.addEventListener("click", function (e) {
      var btn = e.target.closest("[data-approve-order]");
      if (!btn || btn.classList.contains("is-done")) return;
      btn.textContent = "Approved";
      btn.classList.add("is-done");
      btn.disabled = true;
      var send = btn.parentElement.querySelector("[data-send-supplier]");
      if (send) send.classList.remove("hidden");
    });
  }

  function initDishBoxes() {
    document.addEventListener("click", function (e) {
      var box = e.target.closest("[data-dish-group]");
      if (!box) return;
      openSheet("Suggested action", "<p>" + box.getAttribute("data-dish-action") + "</p>");
    });
  }

  function initSalesSimulator() {
    var slider = document.getElementById("pilau-slider");
    var out = document.getElementById("pilau-result");
    if (!slider || !out || !D.sales) return;
    function update() {
      var pct = Number(slider.value);
      var lift = Math.round((D.sales.simulator.baseLift * pct) / 10);
      out.textContent =
        "Sales plus " +
        D.formatKES(lift) +
        " a month. Based on: customers react by about " +
        D.sales.simulator.reaction +
        " for each 1 percent";
    }
    slider.addEventListener("input", update);
    update();
  }

  function initShiftRows() {
    document.addEventListener("click", function (e) {
      var row = e.target.closest("[data-shift-id]");
      if (!row) return;
      var label = row.getAttribute("data-shift-label");
      openSheet(
        label + " shift",
        "<p>Sales " +
          row.getAttribute("data-shift-sales") +
          ". Cash gap " +
          row.getAttribute("data-shift-cash") +
          ". M-Pesa gap " +
          row.getAttribute("data-shift-mpesa") +
          ".</p><p class=\"freshness-line\">From shift close report.</p>"
      );
    });
  }

  function initReportTabs() {
    var wrap = document.getElementById("reports-tabs");
    if (!wrap) return;
    wrap.querySelectorAll(".tabs button").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var tab = btn.getAttribute("data-tab");
        wrap.querySelectorAll(".tabs button").forEach(function (b) {
          b.classList.remove("is-active");
        });
        wrap.querySelectorAll(".tab-panel").forEach(function (p) {
          p.classList.remove("is-active");
        });
        btn.classList.add("is-active");
        var panel = wrap.querySelector('[data-panel="' + tab + '"]');
        if (panel) panel.classList.add("is-active");
      });
    });
  }

  function initSettingsSave() {
    document.querySelectorAll("[data-setting]").forEach(function (input) {
      input.addEventListener("change", function () {
        var line = document.getElementById("settings-saved");
        if (line) line.textContent = "Saved";
      });
    });
  }

  function initCollapsible() {
    document.querySelectorAll("[data-collapsible]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var wrap = btn.closest(".collapsible");
        if (wrap) wrap.classList.toggle("is-open");
      });
    });
  }

  function initHomeDayToggle() {
    var toggle = document.getElementById("day-toggle");
    if (!toggle) return;
    toggle.addEventListener("change", function () {
      var full = document.getElementById("home-full");
      var day1 = document.getElementById("home-day1");
      if (!full || !day1) return;
      if (toggle.checked) {
        full.classList.add("hidden");
        day1.classList.remove("hidden");
      } else {
        full.classList.remove("hidden");
        day1.classList.add("hidden");
      }
    });
  }

  function initAsk() {
    var chat = document.getElementById("chat-messages");
    if (!chat || !D.ask) return;

    function addBubble(text, role) {
      var div = document.createElement("div");
      div.className = "chat-bubble chat-bubble--" + role;
      div.innerHTML = text;
      chat.appendChild(div);
      chat.scrollTop = chat.scrollHeight;
    }

    function formatAnswer(key) {
      var a = D.ask.answers[key];
      if (!a) return "";
      var html = "<p>" + a.sentence + "</p>";
      if (a.number) html += "<p><strong>" + a.number + "</strong></p>";
      if (a.ranked) {
        html += "<ol>";
        a.ranked.forEach(function (r) {
          html += "<li>" + r + "</li>";
        });
        html += "</ol>";
      }
      if (a.table) {
        html += '<table class="spreadsheet-preview"><tbody>';
        a.table.forEach(function (row, i) {
          html += "<tr>";
          row.forEach(function (cell) {
            html += i === 0 ? "<th>" + cell + "</th>" : "<td>" + cell + "</td>";
          });
          html += "</tr>";
        });
        html += "</tbody></table>";
      }
      html += '<p class="freshness-line">Where this comes from: ' + a.source + "</p>";
      if (a.ai) html += '<p class="ai-label">Written by AI</p>';
      if (a.followUp) {
        html +=
          '<button type="button" class="chip" data-followup="' +
          a.followUp +
          '">' +
          a.followUp +
          "</button>";
      }
      return html;
    }

    document.addEventListener("click", function (e) {
      var chip = e.target.closest("[data-ask-chip]");
      if (!chip || !document.getElementById("chat-messages")) return;
      var key = chip.getAttribute("data-ask-chip");
      var label = chip.textContent.trim();
      addBubble(label, "user");
      var typing = document.createElement("div");
      typing.className = "chat-bubble chat-bubble--ai typing-dots";
      typing.textContent = "LEVIII is typing";
      chat.appendChild(typing);
      chat.scrollTop = chat.scrollHeight;
      setTimeout(function () {
        typing.remove();
        addBubble(formatAnswer(key), "ai");
      }, 1000);
    });

    var cantBtn = document.getElementById("ask-cant-example");
    if (cantBtn) {
      cantBtn.addEventListener("click", function () {
        var c = D.ask.answers.cant;
        addBubble(c.question, "user");
        setTimeout(function () {
          addBubble(
            "<p>" +
              c.reply +
              '</p><p class="freshness-line">Where this comes from: ' +
              c.source +
              '</p><p class="ai-label">Written by AI</p>',
            "ai"
          );
        }, 1000);
      });
    }

    chat.addEventListener("click", function (e) {
      var fu = e.target.closest("[data-followup]");
      if (fu) addBubble(fu.getAttribute("data-followup"), "user");
    });
  }

  function initPriceApprove() {
    document.addEventListener("click", function (e) {
      var btn = e.target.closest("[data-price-approve]");
      if (!btn || btn.disabled) return;
      var note = btn.closest(".card").querySelector("[data-till-note]");
      if (note) note.classList.remove("hidden");
      btn.disabled = true;
      btn.textContent = "Approved";
    });
  }

  window.LEVIII = {
    openSheet: openSheet,
    closeSheet: closeSheet,
  };

  document.addEventListener("DOMContentLoaded", function () {
    initNav();
    initSheet();
    bindData();
    initDismissCards();
    initMoneyPeriod();
    initStockApprove();
    initDishBoxes();
    initSalesSimulator();
    initShiftRows();
    initReportTabs();
    initSettingsSave();
    initCollapsible();
    initHomeDayToggle();
    initAsk();
    initPriceApprove();
  });
})();
