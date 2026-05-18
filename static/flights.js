(function () {
  var form = document.getElementById("flightSearch");
  var statusEl = document.getElementById("flightStatus");
  var resultsEl = document.getElementById("flightResults");
  var dateInput = document.getElementById("departure_date");

  function defaultDate() {
    var d = new Date();
    d.setDate(d.getDate() + 14);
    return d.toISOString().slice(0, 10);
  }

  if (dateInput && !dateInput.value) {
    dateInput.value = defaultDate();
  }

  if (dateInput) {
    var today = new Date().toISOString().slice(0, 10);
    dateInput.min = today;
  }

  function setStatus(msg, kind) {
    if (!statusEl) return;
    statusEl.textContent = msg || "";
    statusEl.className = "status" + (kind ? " status--" + kind : "");
  }

  function formatTime(iso) {
    if (!iso) return "—";
    try {
      var d = new Date(iso);
      return d.toLocaleString("es-MX", {
        dateStyle: "short",
        timeStyle: "short",
      });
    } catch (e) {
      return iso;
    }
  }

  function renderOffers(offers) {
    if (!resultsEl) return;
    resultsEl.innerHTML = "";
    if (!offers || offers.length === 0) {
      resultsEl.innerHTML =
        '<p class="results--empty">No se encontraron ofertas para esa ruta y fecha.</p>';
      return;
    }
    offers.forEach(function (o) {
      var div = document.createElement("article");
      div.className = "flight-card";
      div.innerHTML =
        '<div class="flight-card__route">' +
        (o.departure_airport || "?") +
        " → " +
        (o.arrival_airport || "?") +
        "</div>" +
        '<div class="flight-card__meta">Salida: ' +
        formatTime(o.departure_time) +
        " · Llegada: " +
        formatTime(o.arrival_time) +
        "</div>" +
        '<div class="flight-card__meta">Escalas: ' +
        (o.stops ?? 0) +
        (o.carriers ? " · Vuelo: " + o.carriers : "") +
        "</div>" +
        '<div class="flight-card__price">' +
        (o.total != null ? Number(o.total).toFixed(2) : "—") +
        " " +
        (o.currency || "") +
        "</div>";
      resultsEl.appendChild(div);
    });
  }

  if (!form) return;

  form.addEventListener("submit", async function (e) {
    e.preventDefault();
    var fd = new FormData(form);
    var origin = String(fd.get("origin") || "")
      .trim()
      .toUpperCase();
    var destination = String(fd.get("destination") || "")
      .trim()
      .toUpperCase();
    var departure_date = String(fd.get("departure_date") || "").trim();
    var adults = String(fd.get("adults") || "1").trim();

    if (origin.length !== 3 || destination.length !== 3) {
      setStatus("Origen y destino deben ser códigos IATA de 3 letras.", "error");
      return;
    }

    var params = new URLSearchParams({
      origin: origin,
      destination: destination,
      departure_date: departure_date,
      adults: adults,
    });

    var btn = form.querySelector('button[type="submit"]');
    if (btn) btn.disabled = true;
    setStatus("Buscando vuelos…", "ok");
    renderOffers([]);

    try {
      var res = await fetch("/api/flights?" + params.toString());
      var data = await res.json().catch(function () {
        return {};
      });
      if (!res.ok) {
        var detail =
          typeof data.detail === "string" ?
            data.detail :
            JSON.stringify(data.detail || data);
        setStatus("Error: " + detail, "error");
        renderOffers([]);
        return;
      }
      var offers = data.offers || [];
      setStatus(offers.length + " oferta(s) encontrada(s).", "ok");
      renderOffers(offers);
    } catch (err) {
      setStatus("No se pudo conectar al servidor.", "error");
      renderOffers([]);
    } finally {
      if (btn) btn.disabled = false;
    }
  });
})();
