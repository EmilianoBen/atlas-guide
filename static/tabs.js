(function () {
  var tabs = document.querySelectorAll(".topbar__tab");
  var panels = {
    flights: document.getElementById("panelFlights"),
    hotels: document.getElementById("panelHotels"),
    airbnb: document.getElementById("panelAirbnb"),
  };

  function activate(name) {
    tabs.forEach(function (t) {
      var on = t.getAttribute("data-tab") === name;
      t.classList.toggle("is-active", on);
      t.setAttribute("aria-selected", on ? "true" : "false");
    });
    Object.keys(panels).forEach(function (key) {
      var p = panels[key];
      if (!p) return;
      var show = key === name;
      p.hidden = !show;
      p.classList.toggle("search-panel--hidden", !show);
    });
  }

  tabs.forEach(function (tab) {
    tab.addEventListener("click", function () {
      activate(tab.getAttribute("data-tab") || "flights");
    });
  });
})();
