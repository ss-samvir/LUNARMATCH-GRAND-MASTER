/* =========================================================
   LUNARMATCH V2
   GLOBAL LIVE ENVIRONMENT
   ========================================================= */

const cursorGlow = document.getElementById("cursor-glow");

let mouseX = window.innerWidth / 2;
let mouseY = window.innerHeight / 2;

let currentX = mouseX;
let currentY = mouseY;


/* =========================================================
   MOUSE TRACKING
   ========================================================= */

window.addEventListener("mousemove", (event) => {

    mouseX = event.clientX;
    mouseY = event.clientY;

});


/* =========================================================
   SMOOTH CURSOR LIGHT
   ========================================================= */

function animateCursor() {

    currentX += (mouseX - currentX) * 0.08;
    currentY += (mouseY - currentY) * 0.08;

    if (cursorGlow) {

        cursorGlow.style.left = `${currentX}px`;
        cursorGlow.style.top = `${currentY}px`;

    }

    requestAnimationFrame(animateCursor);
}

animateCursor();


/* =========================================================
   SUBTLE PARALLAX
   ========================================================= */

window.addEventListener("mousemove", (event) => {

    const x =
        (event.clientX / window.innerWidth - 0.5) * 2;

    const y =
        (event.clientY / window.innerHeight - 0.5) * 2;


    const back =
        document.querySelector(".stars-back");

    const mid =
        document.querySelector(".stars-mid");

    const front =
        document.querySelector(".stars-front");


    if (back) {

        back.style.transform =
            `translate3d(${x * 8}px, ${y * 8}px, 0)`;

    }


    if (mid) {

        mid.style.transform =
            `translate3d(${x * 16}px, ${y * 16}px, 0)`;

    }


    if (front) {

        front.style.transform =
            `translate3d(${x * 28}px, ${y * 28}px, 0)`;

    }

});
