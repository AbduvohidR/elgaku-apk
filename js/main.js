// ELGAKU landing - mobil menyu
(function () {
  var burger = document.getElementById('burger');
  var nav = document.getElementById('mainNav');
  if (burger && nav) {
    burger.addEventListener('click', function () {
      nav.classList.toggle('open');
    });
  }
})();
