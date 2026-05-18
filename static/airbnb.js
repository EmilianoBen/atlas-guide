(function () {
  var form = document.getElementById("airbnbSearch");
  var statusEl = document.getElementById("airbnbStatus");
  var checkIn = document.getElementById("airbnb_check_in");
  var checkOut = document.getElementById("airbnb_check_out");

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

  if (form) {
    form.addEventListener("submit", async function (e) {
      e.preventDefault();
      var fd = new FormData(form);
      var q = String(fd.get("query") || "").trim();
      var cin = String(fd.get("check_in") || "").trim();
      var cout = String(fd.get("check_out") || "").trim();
      var adults = String(fd.get("adults") || "2").trim();
      var children = String(fd.get("children") || "0").trim();
      var infants = String(fd.get("infants") || "0").trim();

      var params = new URLSearchParams({
        query: q,
        check_in: cin,
        check_out: cout,
        adults: adults,
        children: children,
        infants: infants,
      });

      var btn = form.querySelector('button[type="submit"]');
      if (btn) btn.disabled = true;
      setStatus("Generando enlace…", "ok");

      try {
        var res = await fetch("/api/airbnb-link?" + params.toString());
        var data = await res.json().catch(function () {
          return {};
        });
        if (!res.ok) {
          var detail =
            typeof data.detail === "string" ?
              data.detail :
              JSON.stringify(data.detail || data);
          setStatus("Error: " + detail, "error");
          return;
        }
        if (data.url) {
          setStatus("Abriendo Airbnb en una nueva pestaña…", "ok");
          window.open(data.url, "_blank", "noopener,noreferrer");
        }
      } catch (err) {
        setStatus("No se pudo conectar al servidor.", "error");
      } finally {
        if (btn) btn.disabled = false;
      }
    });
  }
})();
