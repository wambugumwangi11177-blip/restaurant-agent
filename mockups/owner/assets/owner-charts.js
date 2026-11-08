/** Dark-style inline SVG snippets for owner mockups (guide figures). */
(function () {
  "use strict";

  function stockParLineSvg(opts) {
    var w = 300;
    var h = 88;
    var pad = 16;
    var maxY = opts.par * 1.1;
    function y(v) {
      return pad + ((maxY - v) / maxY) * (h - pad * 2);
    }
    var pts = opts.points
      .map(function (v, i) {
        var x = pad + (i / (opts.points.length - 1)) * (w - pad * 2);
        return x + "," + y(v);
      })
      .join(" ");
  return (
      '<svg class="chart-dark guide-chart" viewBox="0 0 ' +
      w +
      " " +
      h +
      '" role="img" aria-label="Stock level over time with reorder and par">' +
      '<line x1="' +
      pad +
      '" y1="' +
      y(opts.reorder) +
      '" x2="' +
      (w - pad) +
      '" y2="' +
      y(opts.reorder) +
      '" stroke="#fde68a" stroke-dasharray="4 3" stroke-width="1"/>' +
      '<text x="' +
      (w - pad) +
      '" y="' +
      (y(opts.reorder) - 4) +
      '" font-size="8" fill="#fde68a" text-anchor="end">Reorder</text>' +
      '<line x1="' +
      pad +
      '" y1="' +
      y(opts.par) +
      '" x2="' +
      (w - pad) +
      '" y2="' +
      y(opts.par) +
      '" stroke="#a1a1aa" stroke-dasharray="4 3" stroke-width="1"/>' +
      '<text x="' +
      (w - pad) +
      '" y="' +
      (y(opts.par) - 4) +
      '" font-size="8" fill="#a1a1aa" text-anchor="end">Par</text>' +
      '<polyline fill="none" stroke="#e4e4e7" stroke-width="2" points="' +
      pts +
      '"/>' +
      '<circle cx="' +
      (w - pad) +
      '" cy="' +
      y(opts.points[opts.points.length - 1]) +
      '" r="3" fill="#fafafa"/>' +
      "</svg>"
    );
  }

  function gapCompareSvg(actual, expected) {
    var w = 280;
    var h = 56;
    var max = Math.max(actual, expected) * 1.1;
    var aw = Math.round((actual / max) * 200);
    var ew = Math.round((expected / max) * 200);
    return (
      '<svg class="chart-dark guide-chart" viewBox="0 0 ' +
      w +
      " " +
      h +
      '" role="img" aria-label="Actual versus expected stock">' +
      '<text x="0" y="14" font-size="9" fill="#a1a1aa">Expected</text>' +
      '<rect x="70" y="4" width="' +
      ew +
      '" height="10" fill="#a1a1aa" rx="2"/>' +
      '<text x="0" y="36" font-size="9" fill="#e4e4e7">Counted</text>' +
      '<rect x="70" y="26" width="' +
      aw +
      '" height="10" fill="#fde68a" rx="2"/>' +
      '<text x="0" y="52" font-size="8" fill="#a1a1aa">' +
      expected +
      " kg should · " +
      actual +
      " kg found</text>" +
      "</svg>"
    );
  }

  function gapCausesSvg(labels) {
    var items = labels.slice(0, 6);
    var cx = 100;
    var cy = 100;
    var r = 78;
    var paths = "";
    var texts = "";
    items.forEach(function (label, i) {
      var a0 = (i / items.length) * Math.PI * 2 - Math.PI / 2;
      var a1 = ((i + 1) / items.length) * Math.PI * 2 - Math.PI / 2;
      var x0 = cx + Math.cos(a0) * r;
      var y0 = cy + Math.sin(a0) * r;
      var x1 = cx + Math.cos(a1) * r;
      var y1 = cy + Math.sin(a1) * r;
      paths +=
        '<path d="M' +
        cx +
        " " +
        cy +
        " L" +
        x0 +
        " " +
        y0 +
        " A" +
        r +
        " " +
        r +
        " 0 0 1 " +
        x1 +
        " " +
        y1 +
        ' Z" fill="rgba(255,255,255,0.08)" stroke="#71717a"/>';
      var am = (a0 + a1) / 2;
      var tx = cx + Math.cos(am) * (r * 0.55);
      var ty = cy + Math.sin(am) * (r * 0.55);
      var short = label.length > 14 ? label.slice(0, 12) + "…" : label;
      texts +=
        '<text x="' +
        tx +
        '" y="' +
        ty +
        '" font-size="7" fill="#e4e4e7" text-anchor="middle">' +
        short +
        "</text>";
    });
    return (
      '<svg class="chart-dark guide-chart" viewBox="0 0 200 200" role="img" aria-label="Possible gap causes">' +
      paths +
      '<circle cx="' +
      cx +
      '" cy="' +
      cy +
      '" r="28" fill="rgba(12,12,14,0.95)" stroke="#fafafa" stroke-width="1"/>' +
      '<text x="' +
      cx +
      '" y="' +
      (cy + 3) +
      '" font-size="8" fill="#fafafa" text-anchor="middle">Gap</text>' +
      texts +
      "</svg>"
    );
  }

  function threeWayMatchSvg() {
    return (
      '<svg class="chart-dark guide-chart" viewBox="0 0 280 140" role="img" aria-label="Till, cash drawer and M-Pesa three-way match">' +
      '<polygon points="140,20 30,120 250,120" fill="none" stroke="#71717a" stroke-width="1"/>' +
      '<line x1="140" y1="20" x2="140" y2="75" stroke="#e4e4e7" stroke-dasharray="3 3"/>' +
      '<line x1="30" y1="120" x2="185" y2="95" stroke="#e4e4e7" stroke-dasharray="3 3"/>' +
      '<line x1="250" y1="120" x2="95" y2="95" stroke="#e4e4e7" stroke-dasharray="3 3"/>' +
      '<text x="140" y="16" font-size="10" fill="#fafafa" text-anchor="middle">Till</text>' +
      '<text x="28" y="132" font-size="10" fill="#fafafa">Cash counted</text>' +
      '<text x="214" y="132" font-size="10" fill="#fafafa">M-Pesa</text>' +
      '<text x="140" y="78" font-size="8" fill="#a1a1aa" text-anchor="middle">Cross-check</text>' +
      "</svg>"
    );
  }

  window.OWNER_CHARTS = {
    stockParLineSvg: stockParLineSvg,
    gapCompareSvg: gapCompareSvg,
    gapCausesSvg: gapCausesSvg,
    threeWayMatchSvg: threeWayMatchSvg,
    targetDialSvg: function (label, value, targetLo, targetHi) {
      var w = 280;
      var barW = w - 40;
      var lo = (targetLo / 100) * barW;
      var hi = (targetHi / 100) * barW;
      var fill = Math.min(barW, (value / 100) * barW);
      var inBand = value >= targetLo && value <= targetHi;
      return (
        '<div class="target-dial"><p class="target-dial__label">' +
        label +
        '</p><div class="target-dial__track"><div class="target-dial__band" style="left:20px;width:' +
        (hi - lo) +
        "px;margin-left:" +
        lo +
        'px"></div><div class="target-dial__fill' +
        (inBand ? " target-dial__fill--ok" : "") +
        '" style="width:' +
        fill +
        'px"></div></div><p class="target-dial__meta">' +
        value +
        "% · your band " +
        targetLo +
        "–" +
        targetHi +
        "%</p></div>"
      );
    },
    dishQuadrantSvg: function (points) {
      var dots = points
        .map(function (p) {
          var x = 20 + p.pop * 1.6;
          var y = 120 - p.margin * 1.1;
          return (
            '<circle cx="' +
            x +
            '" cy="' +
            y +
            '" r="5" fill="#fafafa"/><text x="' +
            (x + 8) +
            '" y="' +
            (y + 3) +
            '" font-size="7" fill="#d4d4d8">' +
            p.label +
            "</text>"
          );
        })
        .join("");
      return (
        '<svg class="chart-dark guide-chart" viewBox="0 0 180 140" role="img" aria-label="Dishes by popularity and margin">' +
        '<line x1="20" y1="120" x2="170" y2="120" stroke="#71717a"/>' +
        '<line x1="20" y1="120" x2="20" y2="10" stroke="#71717a"/>' +
        '<text x="90" y="136" font-size="8" fill="#a1a1aa" text-anchor="middle">Popularity</text>' +
        '<text x="8" y="70" font-size="8" fill="#a1a1aa" transform="rotate(-90 8 70)">Margin</text>' +
        dots +
        "</svg>"
      );
    },
    alertsPyramidSvg: function () {
      return (
        '<svg class="chart-dark guide-chart" viewBox="0 0 260 120" role="img" aria-label="Alert priority levels">' +
        '<polygon points="130,10 40,110 220,110" fill="rgba(253,230,138,0.15)" stroke="#fde68a"/>' +
        '<line x1="65" y1="78" x2="195" y2="78" stroke="#71717a"/>' +
        '<line x1="90" y1="48" x2="170" y2="48" stroke="#71717a"/>' +
        '<text x="130" y="28" font-size="8" fill="#fde68a" text-anchor="middle">Needs you now</text>' +
        '<text x="130" y="62" font-size="8" fill="#e4e4e7" text-anchor="middle">Today summary</text>' +
        '<text x="130" y="102" font-size="8" fill="#a1a1aa" text-anchor="middle">This week</text>' +
        "</svg>"
      );
    },
    reportPeriodsSvg: function () {
      return (
        '<svg class="chart-dark guide-chart" viewBox="0 0 300 72" role="img" aria-label="Report depth by period">' +
        '<rect x="10" y="44" width="50" height="24" fill="#71717a" rx="4"/>' +
        '<rect x="70" y="32" width="60" height="36" fill="#a1a1aa" rx="4"/>' +
        '<rect x="140" y="18" width="70" height="50" fill="#d4d4d8" rx="4"/>' +
        '<rect x="220" y="8" width="70" height="60" fill="#fafafa" rx="4"/>' +
        '<text x="35" y="40" font-size="8" fill="#e4e4e7" text-anchor="middle">Day</text>' +
        '<text x="100" y="28" font-size="8" fill="#e4e4e7" text-anchor="middle">Week</text>' +
        '<text x="175" y="14" font-size="8" fill="#171717" text-anchor="middle">Month</text>' +
        '<text x="255" y="4" font-size="8" fill="#171717" text-anchor="middle">Year</text>' +
        "</svg>"
      );
    },
    billRadarSvg: function (points, bills) {
      var w = 300;
      var h = 90;
      var pad = 14;
      var max = Math.max.apply(null, points);
      var pts = points
        .map(function (v, i) {
          var x = pad + (i / (points.length - 1)) * (w - pad * 2);
          var y = pad + ((max - v) / max) * (h - pad * 2);
          return x + "," + y;
        })
        .join(" ");
      var marks = bills
        .map(function (b) {
          var x = pad + b.idx * ((w - pad * 2) / (points.length - 1));
          return (
            '<line x1="' +
            x +
            '" y1="' +
            pad +
            '" x2="' +
            x +
            '" y2="' +
            (h - pad) +
            '" stroke="#fde68a" stroke-dasharray="2 2"/><text x="' +
            x +
            '" y="' +
            (h - 2) +
            '" font-size="7" fill="#fde68a" text-anchor="middle">' +
            b.label +
            "</text>"
          );
        })
        .join("");
      return (
        '<svg class="chart-dark guide-chart" viewBox="0 0 ' +
        w +
        " " +
        h +
        '" role="img" aria-label="Cash forecast with bills">' +
        '<polyline fill="none" stroke="#e4e4e7" stroke-width="2" points="' +
        pts +
        '"/>' +
        marks +
        "</svg>"
      );
    },
  };
})();
