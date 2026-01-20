let element_dark_button = document.getElementById("black");
console.log(element_dark_button);
element_dark_button.addEventListener("click", function () {
  document.body.style.backgroundColor = "black";
});
let element_white_button = document.getElementById("white");
console.log(element_white_button);
element_white_button.addEventListener("click", function () {
  document.body.style.backgroundColor = "white";
});
