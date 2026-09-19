/* =========================================================
   LUNARMATCH V2 — CORE JAVASCRIPT
   ========================================================= */


/* =========================================================
   GENERIC JSON POST
   ========================================================= */

async function postJSON(url, data) {

  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify(data)
  });

  const result = await response.json();

  if (!response.ok) {
    throw new Error(result.error || "Request failed");
  }

  return result;
}


/* =========================================================
   AUTHENTICATION
   ========================================================= */

function wireAuth() {

  const form = document.querySelector("[data-auth]");

  if (!form) return;

  if (form.dataset.authReady === "true") return;

  form.dataset.authReady = "true";

  form.addEventListener("submit", async event => {

    event.preventDefault();

    const data =
      Object.fromEntries(new FormData(form));

    try {

      await postJSON(
        form.dataset.auth,
        data
      );

      window.location.href = "/analyze";

    } catch (error) {

      const message =
        document.querySelector("#msg");

      if (message) {
        message.textContent =
          error.message;
      }
    }
  });
}


/* =========================================================
   ANALYZE — IMAGE UPLOAD + ANALYSIS REQUEST
   ========================================================= */

function wireAnalyze() {

  const form =
    document.querySelector("#analyzeForm");

  if (!form) return;

  /*
   * Prevent duplicate listeners when the
   * smooth-navigation system replaces a page.
   */

  if (form.dataset.analyzeReady === "true") {
    return;
  }

  form.dataset.analyzeReady = "true";


  const inputs =
    form.querySelectorAll(
      'input[type="file"]'
    );

  const button =
    form.querySelector(
      'button[type="submit"]'
    );

  const message =
    form.querySelector(
      "#analysisMsg"
    );


  /* -------------------------------------------------------
     UPDATE UPLOAD CARD
     ------------------------------------------------------- */

 function updateFileState(input) {

  const file =
    input.files &&
    input.files[0];

  const card =
    input.closest(".lm-upload-card");

  if (!card) return;


  const copy =
    card.querySelector(
      ".lm-upload-copy strong"
    );

  const sub =
    card.querySelector(
      ".lm-upload-copy span"
    );

  const browse =
    card.querySelector(
      ".lm-file-browse"
    );

  const visual =
    card.querySelector(
      ".lm-upload-visual"
    );


  /*
   * Remove any previous preview.
   */

  const oldPreview =
    card.querySelector(
      ".lm-live-preview"
    );

  if (oldPreview) {

    if (oldPreview.dataset.objectUrl) {

      URL.revokeObjectURL(
        oldPreview.dataset.objectUrl
      );
    }

    oldPreview.remove();
  }


  /*
   * No file selected.
   */

  if (!file) {

    card.classList.remove(
      "has-file"
    );

    if (copy) {

      copy.textContent =
        input.name === "image_a"
          ? "DROP IMAGE A"
          : "DROP IMAGE B";
    }

    if (sub) {

      sub.textContent =
        input.name === "image_a"
          ? "or select a lunar observation"
          : "or select a comparison observation";
    }

    if (browse) {

      browse.innerHTML =
        'SELECT FILE <span>↗</span>';
    }

    if (visual) {

      visual.style.display =
        "";
    }

    return;
  }


  /*
   * File selected.
   */

  card.classList.add(
    "has-file"
  );


  const sizeMB =
    file.size /
    (1024 * 1024);


  if (copy) {

    copy.textContent =
      file.name;
  }


  if (sub) {

    sub.textContent =
      `${sizeMB.toFixed(2)} MB · ${file.type || "image"}`;
  }


  if (browse) {

    browse.innerHTML =
      'FILE READY <span>✓</span>';
  }


  /*
   * Create the actual image preview.
   */

  if (
    file.type &&
    file.type.startsWith("image/")
  ) {

    const preview =
      document.createElement("img");

    preview.className =
      "lm-live-preview";

    preview.alt =
      input.name === "image_a"
        ? "Selected Image A preview"
        : "Selected Image B preview";

    const objectUrl =
      URL.createObjectURL(file);

    preview.src =
      objectUrl;

    preview.dataset.objectUrl =
      objectUrl;


    /*
     * Put the preview inside
     * the upload card.
     */

    if (visual) {

      visual.style.display =
        "none";

      visual.insertAdjacentElement(
        "beforebegin",
        preview
      );

    } else {

      card.insertBefore(
        preview,
        card.firstChild
      );
    }
  }
}
  /* -------------------------------------------------------
     FILE INPUT EVENTS
     ------------------------------------------------------- */

  inputs.forEach(input => {

    input.addEventListener(
      "change",
      () => {

        updateFileState(input);

        if (message) {
          message.textContent = "";
        }
      }
    );
  });


  /* -------------------------------------------------------
     FORM SUBMISSION
     ------------------------------------------------------- */

  form.addEventListener(
    "submit",
    async event => {

      event.preventDefault();


      const imageA =
        form.querySelector(
          'input[name="image_a"]'
        );

      const imageB =
        form.querySelector(
          'input[name="image_b"]'
        );


      /*
       * Both images required
       */

      if (
        !imageA?.files?.length ||
        !imageB?.files?.length
      ) {

        if (message) {

          message.textContent =
            "Please select both Image A and Image B.";
        }

        return;
      }


      const fileA =
        imageA.files[0];

      const fileB =
        imageB.files[0];


      /*
       * Maximum upload size
       *
       * Flask is also configured for
       * 25 MB, so the browser checks it
       * before making the request.
       */

      const maxSize =
        25 * 1024 * 1024;


      if (
        fileA.size > maxSize ||
        fileB.size > maxSize
      ) {

        if (message) {

          message.textContent =
            "Each image must be 25 MB or smaller.";
        }

        return;
      }


      /*
       * Basic browser-side image validation
       */

      if (
        !fileA.type.startsWith("image/") ||
        !fileB.type.startsWith("image/")
      ) {

        if (message) {

          message.textContent =
            "Please select valid image files.";
        }

        return;
      }


      /*
       * Processing state
       */

      const originalHTML =
        button
          ? button.innerHTML
          : "";


      if (button) {

        button.disabled = true;

        button.classList.add(
          "is-processing"
        );

        button.innerHTML =
          '<span class="lm-run-icon">◌</span>' +
          '<span>ANALYZING OBSERVATIONS…</span>';
      }


      if (message) {

        message.textContent =
          "Uploading observations and starting correspondence analysis…";
      }


      try {

        /*
         * FormData automatically includes:
         *
         * image_a
         * image_b
         */

        const formData =
          new FormData(form);


        const response =
          await fetch(
            "/api/analyze",
            {
              method: "POST",
              body: formData
            }
          );


        /*
         * Try to read JSON safely.
         */

        let data;

        try {

          data =
            await response.json();

        } catch {

          throw new Error(
            "The analysis server returned an invalid response."
          );
        }


        if (!response.ok) {

          throw new Error(
            data.error ||
            "Analysis request failed."
          );
        }


        /*
         * Preserve complete result
         * for the Results page.
         */

        sessionStorage.setItem(
          "lm_result",
          JSON.stringify(data)
        );


        if (message) {

          message.textContent =
            "Analysis complete. Opening evidence report…";
        }


        window.location.href =
          "/results";


      } catch (error) {

        console.error(
          "LUNARMATCH analysis error:",
          error
        );


        if (message) {

          message.textContent =
            error.message ||
            "Unable to complete the analysis.";
        }


        if (button) {

          button.disabled = false;

          button.classList.remove(
            "is-processing"
          );

          button.innerHTML =
            originalHTML;
        }
      }
    }
  );
}


/* =========================================================
   RESULTS PAGE
   ========================================================= */

function renderResult() {

  const box =
    document.querySelector("#result");

  if (!box) return;


  const raw =
    sessionStorage.getItem(
      "lm_result"
    );


  const result =
    raw
      ? JSON.parse(raw)
      : null;


  /*
   * No result available
   */

  if (!result) {

    box.innerHTML = `
      <div class="card">
        <h3>No recent analysis</h3>
        <p class="muted">
          Run an analysis first.
        </p>
      </div>
    `;

    return;
  }


  /*
   * Metadata table
   */

  const metadataTable =
    metadata => {

      const data =
        metadata || {};


      return `
        <table class="table">

          <tr>
            <th>Latitude</th>
            <td>
              ${data.latitude ?? "Not available"}
            </td>
          </tr>

          <tr>
            <th>Longitude</th>
            <td>
              ${data.longitude ?? "Not available"}
            </td>
          </tr>

          <tr>
            <th>Altitude</th>
            <td>
              ${data.altitude ?? "Not available"}
            </td>
          </tr>

          <tr>
            <th>Acquisition</th>
            <td>
              ${data.acquisition_time ?? "Not available"}
            </td>
          </tr>

          <tr>
            <th>CRS / Projection</th>
            <td>
              ${data.crs ?? "Not available"}
              /
              ${data.projection ?? "Not available"}
            </td>
          </tr>

          <tr>
            <th>Mission / Instrument</th>
            <td>
              ${data.mission ?? "Not available"}
              /
              ${data.camera ?? "Not available"}
            </td>
          </tr>

        </table>
      `;
    };


  box.innerHTML = `

    <div class="metrics">

      <div class="card metric">
        <span class="muted">
          RELIABILITY
        </span>

        <strong>
          ${result.reliability}
        </strong>
      </div>


      <div class="card metric">
        <span class="muted">
          SCORE
        </span>

        <strong>
          ${result.score}%
        </strong>
      </div>


      <div class="card metric">
        <span class="muted">
          VERIFIED
        </span>

        <strong>
          ${result.verified_matches}
        </strong>
      </div>


      <div class="card metric">
        <span class="muted">
          INLIER RATIO
        </span>

        <strong>
          ${result.inlier_ratio}%
        </strong>
      </div>

    </div>


    <br>


    <div class="card">

      <h2>
        Correspondence Map
      </h2>

      <img
        class="imgresult"
        src="${result.result_image}"
        alt="Lunar correspondence visualization"
      >

      <p class="muted">
        ${result.validation_note}
      </p>

    </div>


    <br>


    <div class="grid">


      <div class="card">

        <h2>
          Image A Metadata
        </h2>

        ${metadataTable(
          result.image_a?.metadata
        )}

      </div>


      <div class="card">

        <h2>
          Image B Metadata
        </h2>

        ${metadataTable(
          result.image_b?.metadata
        )}

      </div>


      <div class="card">

        <h2>
          Verification
        </h2>


        <table class="table">

          <tr>
            <th>Raw matches</th>
            <td>
              ${result.raw_matches}
            </td>
          </tr>


          <tr>
            <th>Candidate matches</th>
            <td>
              ${result.candidate_matches}
            </td>
          </tr>


          <tr>
            <th>Geometric consistency</th>
            <td>
              ${result.geometric_consistency}%
            </td>
          </tr>


          <tr>
            <th>Feature coverage</th>
            <td>
              ${result.feature_coverage}%
            </td>
          </tr>


          <tr>
            <th>Homography</th>
            <td>
              ${result.homography_status}
            </td>
          </tr>


          <tr>
            <th>Processing</th>
            <td>
              ${result.processing_time_ms} ms
            </td>
          </tr>

        </table>

      </div>

    </div>
  `;
}


/* =========================================================
   STAR-FIELD PARALLAX
   ========================================================= */

function parallax() {

  const back =
    document.querySelector(
      ".star-layer-a"
    );

  const mid =
    document.querySelector(
      ".star-layer-b"
    );

  const front =
    document.querySelector(
      ".star-layer-c"
    );


  if (!back) return;


  let targetX = 0;
  let targetY = 0;

  let currentX = 0;
  let currentY = 0;


  window.addEventListener(
    "pointermove",
    event => {

      targetX =
        (event.clientX /
          window.innerWidth -
          0.5) * 2;

      targetY =
        (event.clientY /
          window.innerHeight -
          0.5) * 2;
    },
    { passive: true }
  );


  function frame() {

    currentX +=
      (targetX - currentX) *
      0.035;

    currentY +=
      (targetY - currentY) *
      0.035;


    back.style.transform =
      `translate3d(
        ${currentX * 5}px,
        ${currentY * 5}px,
        0
      )`;


    if (mid) {

      mid.style.transform =
        `translate3d(
          ${currentX * 11}px,
          ${currentY * 11}px,
          0
        )`;
    }


    if (front) {

      front.style.transform =
        `translate3d(
          ${currentX * 18}px,
          ${currentY * 18}px,
          0
        )`;
    }


    requestAnimationFrame(
      frame
    );
  }


  frame();
}


/* =========================================================
   CURSOR GLOW
   ========================================================= */

function cursor() {

  const glow =
    document.querySelector(
      "#cursor-glow"
    );

  if (!glow) return;


  let targetX =
    window.innerWidth / 2;

  let targetY =
    window.innerHeight / 2;

  let currentX =
    targetX;

  let currentY =
    targetY;


  window.addEventListener(
    "pointermove",
    event => {

      targetX =
        event.clientX;

      targetY =
        event.clientY;
    },
    { passive: true }
  );


  function animate() {

    currentX +=
      (targetX - currentX) *
      0.07;

    currentY +=
      (targetY - currentY) *
      0.07;


    glow.style.left =
      currentX + "px";

    glow.style.top =
      currentY + "px";


    requestAnimationFrame(
      animate
    );
  }


  animate();
}


/* =========================================================
   SMOOTH SAME-ORIGIN NAVIGATION
   ========================================================= */

function lmSmoothNavigation() {


  async function loadPage(
    url,
    push = true
  ) {

    try {

      const response =
        await fetch(
          url,
          {
            headers: {
              "X-Requested-With":
                "XMLHttpRequest"
            }
          }
        );


      if (!response.ok) {

        window.location.href =
          url;

        return;
      }


      const html =
        await response.text();


      const parser =
        new DOMParser();


      const documentPage =
        parser.parseFromString(
          html,
          "text/html"
        );


      const newContent =
        documentPage.querySelector(
          "#page-content"
        );


      const currentContent =
        document.querySelector(
          "#page-content"
        );


      if (
        !newContent ||
        !currentContent
      ) {

        window.location.href =
          url;

        return;
      }


      currentContent.innerHTML =
        newContent.innerHTML;


      document.title =
        documentPage.title;


      if (push) {

        history.pushState(
          {},
          "",
          url
        );
      }


      window.scrollTo(
        0,
        0
      );


      /*
       * Reinitialize page-specific
       * functionality after replacing
       * page content.
       */

      wireAuth();
      wireAnalyze();
      renderResult();
      initProceduralMoon();


      document
        .querySelectorAll(".reveal")
        .forEach(
          (element, index) => {

            element.style.animationDelay =
              `${index * 70}ms`;

            element.classList.add(
              "is-visible"
            );
          }
        );


    } catch (error) {

      console.error(
        "LUNARMATCH navigation error:",
        error
      );

      window.location.href =
        url;
    }
  }


  /*
   * Intercept internal navigation.
   */

  document.addEventListener(
    "click",
    event => {

      const link =
        event.target.closest(
          "a[href]"
        );


      if (!link) return;


      const href =
        link.getAttribute(
          "href"
        );


      if (
        !href ||
        href.startsWith("#") ||
        href.startsWith("http") ||
        href.startsWith("mailto:") ||
        href.startsWith("tel:") ||
        link.target === "_blank" ||
        link.hasAttribute("download")
      ) {

        return;
      }


      const url =
        new URL(
          href,
          window.location.origin
        );


      if (
        url.origin !==
        window.location.origin
      ) {

        return;
      }


      event.preventDefault();

      loadPage(
        url.href
      );
    }
  );


  /*
   * Browser back / forward.
   */

  window.addEventListener(
    "popstate",
    () => {

      loadPage(
        window.location.href,
        false
      );
    }
  );
}


/* =========================================================
   MOBILE NAVIGATION
   ========================================================= */

function lmMobileNavigation() {

  const toggle =
    document.querySelector(
      ".mobile-menu-toggle"
    );

  const menu =
    document.querySelector(
      "#mobile-navigation"
    );


  if (
    !toggle ||
    !menu
  ) {

    return;
  }


  if (
    toggle.dataset.mobileReady ===
    "true"
  ) {

    return;
  }


  toggle.dataset.mobileReady =
    "true";


  function openMenu() {

    toggle.classList.add(
      "is-open"
    );

    menu.classList.add(
      "is-open"
    );


    toggle.setAttribute(
      "aria-expanded",
      "true"
    );


    toggle.setAttribute(
      "aria-label",
      "Close navigation"
    );


    menu.setAttribute(
      "aria-hidden",
      "false"
    );


    document.body.classList.add(
      "mobile-nav-open"
    );
  }


  function closeMenu() {

    toggle.classList.remove(
      "is-open"
    );

    menu.classList.remove(
      "is-open"
    );


    toggle.setAttribute(
      "aria-expanded",
      "false"
    );


    toggle.setAttribute(
      "aria-label",
      "Open navigation"
    );


    menu.setAttribute(
      "aria-hidden",
      "true"
    );


    document.body.classList.remove(
      "mobile-nav-open"
    );
  }


  toggle.addEventListener(
    "click",
    event => {

      event.preventDefault();
      event.stopPropagation();


      if (
        menu.classList.contains(
          "is-open"
        )
      ) {

        closeMenu();

      } else {

        openMenu();
      }
    }
  );


  menu
    .querySelectorAll("a")
    .forEach(link => {

      link.addEventListener(
        "click",
        () => {

          closeMenu();
        }
      );
    });


  document.addEventListener(
    "keydown",
    event => {

      if (
        event.key === "Escape" &&
        menu.classList.contains(
          "is-open"
        )
      ) {

        closeMenu();
      }
    }
  );
}


/* =========================================================
   PROCEDURAL LUNAR SPHERE
   ========================================================= */

function initProceduralMoon() {

  const canvas =
    document.getElementById(
      "lunar-surface-canvas"
    );


  if (!canvas) return;


  if (
    canvas.dataset.ready ===
    "true"
  ) {

    return;
  }


  canvas.dataset.ready =
    "true";


  const context =
    canvas.getContext("2d");


  const container =
    canvas.parentElement;


  if (!context || !container) {
    return;
  }


  let width = 0;
  let height = 0;
  let dpr = 1;

  let rotation = 0;


  const craters = [];


  /*
   * Stable lunar terrain.
   */

  for (
    let i = 0;
    i < 95;
    i++
  ) {

    craters.push({

      longitude:
        Math.random() *
        Math.PI *
        2,

      latitude:
        (Math.random() - 0.5) *
        Math.PI,

      radius:
        0.012 +
        Math.random() *
        0.045,

      depth:
        0.25 +
        Math.random() *
        0.65
    });
  }


  function resize() {

    const rect =
      container.getBoundingClientRect();


    const size =
      Math.max(
        120,
        Math.min(
          rect.width,
          rect.height
        )
      );


    dpr =
      Math.min(
        window.devicePixelRatio ||
          1,
        2
      );


    width =
      size;

    height =
      size;


    canvas.width =
      Math.floor(
        size * dpr
      );

    canvas.height =
      Math.floor(
        size * dpr
      );


    canvas.style.width =
      size + "px";

    canvas.style.height =
      size + "px";


    context.setTransform(
      dpr,
      0,
      0,
      dpr,
      0,
      0
    );
  }


  function draw() {

    const size =
      Math.min(
        width,
        height
      );


    const centerX =
      size / 2;

    const centerY =
      size / 2;


    const radius =
      size * 0.495;


    context.clearRect(
      0,
      0,
      width,
      height
    );


    /*
     * Base spherical shading.
     */

    const sphere =
      context.createRadialGradient(

        centerX -
          radius * 0.30,

        centerY -
          radius * 0.32,

        radius * 0.04,

        centerX,
        centerY,

        radius * 1.05
      );


    sphere.addColorStop(
      0,
      "#d8dce1"
    );

    sphere.addColorStop(
      0.34,
      "#a1a7ae"
    );

    sphere.addColorStop(
      0.68,
      "#666e78"
    );

    sphere.addColorStop(
      0.88,
      "#343c47"
    );

    sphere.addColorStop(
      1,
      "#0d131c"
    );


    context.beginPath();

    context.arc(
      centerX,
      centerY,
      radius,
      0,
      Math.PI * 2
    );

    context.fillStyle =
      sphere;

    context.fill();


    /*
     * Rotating lunar terrain.
     */

    context.save();


    context.beginPath();

    context.arc(
      centerX,
      centerY,
      radius * 0.995,
      0,
      Math.PI * 2
    );

    context.clip();


    for (
      const crater of craters
    ) {

      const longitude =
        crater.longitude +
        rotation;


      const x =
        Math.sin(longitude) *
        Math.cos(
          crater.latitude
        );


      const z =
        Math.cos(longitude) *
        Math.cos(
          crater.latitude
        );


      /*
       * Hide far side.
       */

      if (z < -0.05) {
        continue;
      }


      const y =
        Math.sin(
          crater.latitude
        );


      const px =
        centerX +
        x *
        radius *
        0.94;


      const py =
        centerY -
        y *
        radius *
        0.94;


      const perspective =
        0.72 +
        z *
        0.28;


      const craterRadius =
        radius *
        crater.radius *
        perspective;


      const gradient =
        context.createRadialGradient(

          px -
            craterRadius *
            0.25,

          py -
            craterRadius *
            0.25,

          craterRadius *
            0.05,

          px,
          py,

          craterRadius
        );


      gradient.addColorStop(
        0,
        `rgba(225,229,234,${0.08 * crater.depth})`
      );

      gradient.addColorStop(
        0.45,
        `rgba(55,61,68,${0.22 * crater.depth})`
      );

      gradient.addColorStop(
        0.78,
        `rgba(20,25,31,${0.34 * crater.depth})`
      );

      gradient.addColorStop(
        1,
        "rgba(0,0,0,0)"
      );


      context.fillStyle =
        gradient;


      context.beginPath();

      context.arc(
        px,
        py,
        craterRadius,
        0,
        Math.PI * 2
      );

      context.fill();


      /*
       * Crater rim.
       */

      context.strokeStyle =
        `rgba(220,225,230,${0.08 * crater.depth})`;


      context.lineWidth =
        Math.max(
          0.5,
          craterRadius *
            0.055
        );


      context.beginPath();

      context.arc(
        px -
          craterRadius *
          0.10,

        py -
          craterRadius *
          0.10,

        craterRadius *
          0.68,

        0,
        Math.PI * 2
      );

      context.stroke();
    }


    context.restore();


    /*
     * Fine spherical grain.
     */

    const grain =
      context.createRadialGradient(

        centerX -
          radius * 0.18,

        centerY -
          radius * 0.20,

        radius * 0.05,

        centerX,
        centerY,

        radius
      );


    grain.addColorStop(
      0,
      "rgba(255,255,255,.035)"
    );

    grain.addColorStop(
      0.55,
      "rgba(255,255,255,.01)"
    );

    grain.addColorStop(
      1,
      "rgba(0,0,0,.08)"
    );


    context.beginPath();

    context.arc(
      centerX,
      centerY,
      radius,
      0,
      Math.PI * 2
    );

    context.fillStyle =
      grain;

    context.fill();


    /*
     * Very slow rotation.
     */

    rotation +=
      0.00075;


    requestAnimationFrame(
      draw
    );
  }


  resize();


  window.addEventListener(
    "resize",
    resize,
    {
      passive: true
    }
  );


  requestAnimationFrame(
    draw
  );
}


/* =========================================================
   PAGE INITIALIZATION
   ========================================================= */

function initializeLunarMatch() {

  wireAuth();

  wireAnalyze();

  renderResult();

  lmMobileNavigation();

  initProceduralMoon();
}


/* =========================================================
   INITIAL PAGE LOAD
   ========================================================= */

document.addEventListener(
  "DOMContentLoaded",
  () => {

    initializeLunarMatch();

    parallax();

    cursor();

    lmSmoothNavigation();

    requestAnimationFrame(
      () => {

        document.body.classList.add(
          "lm-ready"
        );
      }
    );
  }
);
