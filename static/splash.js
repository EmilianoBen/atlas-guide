(function () {
  var splash = document.getElementById("splash");
  var shell = document.getElementById("appShell");
  var btn = document.getElementById("btnContinuar");

  function cerrarSplash() {
    if (!splash || splash.classList.contains("is-hidden")) return;
    splash.classList.add("is-hidden");
    if (shell) {
      shell.hidden = false;
    }
    window.setTimeout(function () {
      splash.style.display = "none";
    }, 700);
  }

  if (btn) {
    btn.addEventListener("click", cerrarSplash);
  }

  window.setTimeout(cerrarSplash, 3500);
})();
