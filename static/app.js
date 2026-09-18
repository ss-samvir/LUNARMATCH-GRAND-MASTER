```javascript id="z7q2mx"
/* =========================================================
   LUNARMATCH — SPACE VISUAL ENGINE
   Appearance / animation layer
   ========================================================= */

document.addEventListener("DOMContentLoaded", () => {

    /* =====================================================
       MOBILE NAVIGATION
       ===================================================== */

    const menuButton = document.querySelector(".mobile-menu-btn");
    const navLinks = document.querySelector(".nav-links");

    if (menuButton && navLinks) {
        menuButton.addEventListener("click", () => {
            navLinks.classList.toggle("open");
        });

        navLinks.querySelectorAll("a").forEach(link => {
            link.addEventListener("click", () => {
                navLinks.classList.remove("open");
            });
        });
    }


    /* =====================================================
       SPACE CANVAS
       ===================================================== */

    const canvas = document.getElementById("spaceCanvas");

    if (!canvas) {
        return;
    }

    const ctx = canvas.getContext("2d");

    if (!ctx) {
        return;
    }

    let width = 0;
    let height = 0;
    let stars = [];

    const mouse = {
        x: 0,
        y: 0,
        active: false
    };

    const STAR_COUNT = window.innerWidth < 700 ? 90 : 180;


    /* =====================================================
       RESIZE
       ===================================================== */

    function resizeCanvas() {
        const ratio = Math.min(window.devicePixelRatio || 1, 2);

        width = window.innerWidth;
        height = window.innerHeight;

        canvas.width = width * ratio;
        canvas.height = height * ratio;

        canvas.style.width = `${width}px`;
        canvas.style.height = `${height}px`;

        ctx.setTransform(ratio, 0, 0, ratio, 0, 0);

        createStars();
    }


    /* =====================================================
       STAR GENERATION
       ===================================================== */

    function createStars() {
        stars = [];

        for (let i = 0; i < STAR_COUNT; i++) {

            stars.push({
                x: Math.random() * width,
                y: Math.random() * height,

                size: Math.random() * 1.7 + 0.25,

                speed:
                    Math.random() * 0.22 +
                    0.035,

                opacity:
                    Math.random() * 0.7 +
                    0.15,

                twinkle:
                    Math.random() * Math.PI * 2,

                twinkleSpeed:
                    Math.random() * 0.025 +
                    0.005,

                depth:
                    Math.random() * 0.9 +
                    0.1
            });
        }
    }


    /* =====================================================
       MOUSE PARALLAX
       ===================================================== */

    window.addEventListener("mousemove", event => {

        mouse.x = event.clientX;
        mouse.y = event.clientY;
        mouse.active = true;

    });

    window.addEventListener("mouseleave", () => {
        mouse.active = false;
    });


    /* =====================================================
       DRAW STARS
       ===================================================== */

    function drawStars(time) {

        ctx.clearRect(0, 0, width, height);

        const normalizedMouseX =
            mouse.active
                ? (mouse.x / width - 0.5)
                : 0;

        const normalizedMouseY =
            mouse.active
                ? (mouse.y / height - 0.5)
                : 0;


        stars.forEach(star => {

            star.y -= star.speed;

            if (star.y < -5) {
                star.y = height + 5;
                star.x = Math.random() * width;
            }


            const parallaxX =
                normalizedMouseX *
                star.depth *
                13;

            const parallaxY =
                normalizedMouseY *
                star.depth *
                8;


            const twinkle =
                Math.sin(
                    time * star.twinkleSpeed +
                    star.twinkle
                );

            const alpha =
                Math.max(
                    0.08,
                    star.opacity +
                    twinkle * 0.18
                );


            ctx.beginPath();

            ctx.arc(
                star.x + parallaxX,
                star.y + parallaxY,
                star.size,
                0,
                Math.PI * 2
            );

            ctx.fillStyle =
                `rgba(205,235,255,${alpha})`;

            ctx.fill();
        });
    }


    /* =====================================================
       DISTANT NEBULA
       ===================================================== */

    function drawNebula(time) {

        const driftX =
            Math.sin(time * 0.00008) * 45;

        const driftY =
            Math.cos(time * 0.00006) * 25;


        const gradient1 =
            ctx.createRadialGradient(
                width * 0.18 + driftX,
                height * 0.20 + driftY,
                0,
                width * 0.18 + driftX,
                height * 0.20 + driftY,
                width * 0.38
            );

        gradient1.addColorStop(
            0,
            "rgba(30,130,255,0.075)"
        );

        gradient1.addColorStop(
            0.45,
            "rgba(40,80,220,0.025)"
        );

        gradient1.addColorStop(
            1,
            "rgba(0,0,0,0)"
        );


        ctx.fillStyle = gradient1;
        ctx.fillRect(0, 0, width, height);


        const gradient2 =
            ctx.createRadialGradient(
                width * 0.82 - driftX,
                height * 0.30,
                0,
                width * 0.82 - driftX,
                height * 0.30,
                width * 0.30
            );

        gradient2.addColorStop(
            0,
            "rgba(120,80,255,0.055)"
        );

        gradient2.addColorStop(
            0.55,
            "rgba(80,70,220,0.018)"
        );

        gradient2.addColorStop(
            1,
            "rgba(0,0,0,0)"
        );


        ctx.fillStyle = gradient2;
        ctx.fillRect(0, 0, width, height);
    }


    /* =====================================================
       ORBITAL RINGS
       ===================================================== */

    function drawOrbits(time) {

        if (width < 600) {
            return;
        }

        const centerX =
            width * 0.82;

        const centerY =
            height * 0.34;


        const rotation =
            time * 0.000035;


        ctx.save();

        ctx.translate(centerX, centerY);
        ctx.rotate(rotation);


        ctx.strokeStyle =
            "rgba(70,205,255,0.075)";

        ctx.lineWidth = 1;


        ctx.beginPath();

        ctx.ellipse(
            0,
            0,
            245,
            85,
            0,
            0,
            Math.PI * 2
        );

        ctx.stroke();


        ctx.rotate(Math.PI / 3.2);

        ctx.strokeStyle =
            "rgba(120,105,255,0.055)";

        ctx.beginPath();

        ctx.ellipse(
            0,
            0,
            310,
            105,
            0,
            0,
            Math.PI * 2
        );

        ctx.stroke();


        ctx.restore();
    }


    /* =====================================================
       ANIMATION LOOP
       ===================================================== */

    function animate(time) {

        drawNebula(time);
        drawStars(time);
        drawOrbits(time);

        requestAnimationFrame(animate);
    }


    /* =====================================================
       START
       ===================================================== */

    resizeCanvas();

    window.addEventListener(
        "resize",
        resizeCanvas
    );

    requestAnimationFrame(animate);

});
```
