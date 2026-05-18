(function () {
  var form = document.getElementById("hotelSearch");
  var statusEl = document.getElementById("hotelStatus");
  var resultsEl = document.getElementById("hotelResults");
  var checkIn = document.getElementById("check_in");
  var checkOut = document.getElementById("check_out");
  var btnAirbnb = document.getElementById("btnAirbnb");

  function setStatus(msg, kind) {
    if (!statusEl) return;
    statusEl.textContent = msg || "";
    statusEl.className = "status" + (kind ? " status--" + kind : "");
  }

  function defaultDates() {
    var a = new Date();
    a.setDate(a.getDate() + 14);
    var b = new Date();
    b.setDate(b.getDate() + 17);
    return {
      inStr: a.toISOString().slice(0, 10),
      outStr: b.toISOString().slice(0, 10),
    };
  }

  if (checkIn && !checkIn.value) {
    var d = defaultDates();
    checkIn.value = d.inStr;
    checkOut.value = d.outStr;
  }

  var today = new Date().toISOString().slice(0, 10);
  if (checkIn) checkIn.min = today;
  if (checkOut) checkOut.min = today;

  if (checkIn) {
    checkIn.addEventListener("change", function () {
      if (checkOut && checkOut.value && checkOut.value <= checkIn.value) {
        var t = new Date(checkIn.value);
        t.setDate(t.getDate() + 1);
        checkOut.value = t.toISOString().slice(0, 10);
      }
      if (checkOut) checkOut.min = checkIn.value;
    });
  }

  function renderHotels(list) {
    if (!resultsEl) return;
    resultsEl.innerHTML = "";
    if (!list || list.length === 0) {
      resultsEl.innerHTML =
        '<p class="results--empty">No hay hoteles para esos datos. Prueba otra ciudad, fechas o ampliar el radio (backend).</p>';
      return;
    }
    list.forEach(function (h) {
      var card = document.createElement("article");
      card.className = "hotel-card";
      var img =
        h.photo_url ?
          '<img class="hotel-card__img" src="' +
          String(h.photo_url).replace(/"/g, "") +
          '" alt="" loading="lazy" />' +
          (h.photo_caption ?
            '<p class="hotel-card__caption">' +
            String(h.photo_caption).replace(/</g, "&lt;") +
            "</p>" :
            "") :
          '<div class="hotel-card__placeholder">Sin vista de mapa</div>';
      var score =
        h.review_score != null ?
          '<span class="hotel-card__score">' +
          Number(h.review_score).toFixed(1) +
          " ★</span>" :
          "";
      var loc = [h.city, h.country].filter(Boolean).join(", ");
      card.innerHTML =
        img +
        '<div class="hotel-card__body">' +
        '<h3 class="hotel-card__title">' +
        (h.name || "Alojamiento") +
        "</h3>" +
        "<p class=\"hotel-card__meta\">" +
        (loc || h.address_line || "") +
        "</p>" +
        (h.description ?
          '<p class="hotel-card__desc">' +
          h.description +
          (h.description.length >= 280 ? "…" : "") +
          "</p>" :
          "") +
        '<p class="hotel-card__price">' +
        (h.total != null ?
          Number(h.total).toFixed(2) + " " + (h.currency || "") + " (aprox.)" :
          "Precio no disponible por API") +
        score +
        "</p>" +
        (h.maps_url ?
          '<p class="hotel-card__meta"><a href="' +
          h.maps_url.replace(/"/g, "") +
          '" target="_blank" rel="noopener">Ver en mapa</a></p>' :
          "") +
        "</div>";
      resultsEl.appendChild(card);
    });
  }

  if (form) {
    form.addEventListener("submit", async function (e) {
      e.preventDefault();
      var fd = new FormData(form);
      var city = String(fd.get("city") || "").trim();
      var cin = String(fd.get("check_in") || "").trim();
      var cout = String(fd.get("check_out") || "").trim();
      var guests = String(fd.get("guests") || "2").trim();
      var rooms = String(fd.get("rooms") || "1").trim();

      var params = new URLSearchParams({
        city: city,
        check_in: cin,
        check_out: cout,
        guests: guests,
        rooms: rooms,
      });

      var btn = form.querySelector('button[type="submit"]');
      if (btn) btn.disabled = true;
      setStatus("Buscando hoteles…", "ok");
      renderHotels([]);

      try {
        var res = await fetch("/api/hotels?" + params.toString());
        var data = await res.json().catch(function () {
          return {};
        });
        if (!res.ok) {
          var detail =
            typeof data.detail === "string" ?
              data.detail :
              JSON.stringify(data.detail || data);
          setStatus("Error: " + detail, "error");
          renderHotels([]);
          return;
        }
        var hotels = data.hotels || [];
        var note = data.note ? " " + data.note : "";
        setStatus(hotels.length + " alojamiento(s) encontrado(s)." + note, "ok");
        renderHotels(hotels);
      } catch (err) {
        setStatus("No se pudo conectar al servidor.", "error");
        renderHotels([]);
      } finally {
        if (btn) btn.disabled = false;
      }
    });
  }

  if (btnAirbnb) {
    btnAirbnb.addEventListener("click", async function () {
      var cityEl = document.getElementById("hotel_city");
      var q = cityEl ? String(cityEl.value || "").trim() : "";
      var cin = checkIn ? checkIn.value : "";
      var cout = checkOut ? checkOut.value : "";
      var g = document.getElementById("hotel_guests");
      var adults = g ? String(g.value || "2") : "2";
      if (!q || !cin || !cout) {
        alert("Completa ciudad, entrada y salida en la pestaña Hoteles.");
        return;
      }
      try {
        var params = new URLSearchParams({
          query: q,
          check_in: cin,
          check_out: cout,
          adults: adults,
        });
        var res = await fetch("/api/airbnb-link?" + params.toString());
        var data = await res.json();
        if (data.url) {
          window.open(data.url, "_blank", "noopener,noreferrer");
        }
      } catch (e) {
        alert("No se pudo generar el enlace.");
      }
    });
  }
})();
