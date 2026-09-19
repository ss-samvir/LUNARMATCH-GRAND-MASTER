/* =========================================================
   LUNARMATCH V2 — CORE JAVASCRIPT
   ========================================================= */

/* =========================================================
   GENERIC JSON POST
   ========================================================= */
async function postJSON(url, data) {
  const response = await fetch(url, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
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
  if (!form || form.dataset.authReady === "true") return;

  form.dataset.authReady = "true";

  form.addEventListener("submit", async event => {
    event.preventDefault();

    const data = Object.fromEntries(new FormData(form));

    try {
      await postJSON(form.dataset.auth, data);
      window.location.href = "/analyze";
    } catch (error) {
      const message = document.querySelector("#msg");
      if (message) message.textContent = error.message;
    }
  });
}

/* =========================================================
   ANALYZE — IMAGE UPLOAD + LIVE IMAGE PREVIEW
   ========================================================= */
function wireAnalyze() {
  const form = document.querySelector("#analyzeForm");
  if (!form || form.dataset.analyzeReady === "true") return;

  form.dataset.analyzeReady = "true";

  const inputs = form.querySelectorAll('input[type="file"]');
  const button = form.querySelector('button[type="submit"]');
  const message = form.querySelector("#analysisMsg");

  function updateFileState(input) {
    const file = input.files && input.files[0];
    const card = input.closest(".lm-upload-card");
    if (!card) return;

    const copy = card.querySelector(".lm-upload-copy strong");
    const sub = card.querySelector(".lm-upload-copy span");
    const browse = card.querySelector(".lm-file-browse");

    let preview = card.querySelector(".lm-live-preview");
    let emptyVisual = card.querySelector(".lm-upload-visual");

    if (!file) {
      card.classList.remove("has-file");

      if (copy) {
        copy.textContent =
          input.name === "image_a" ? "DROP IMAGE A" : "DROP IMAGE B";
      }

      if (sub) {
        sub.textContent =
          input.name === "image_a"
            ? "or select a lunar observation"
            : "or select a comparison observation";
      }

      if (browse) {
        browse.innerHTML = 'SELECT FILE <span>↗</span>';
      }

      if (preview) {
        preview.remove();
      }

      if (emptyVisual) {
        emptyVisual.style.display = "";
      }

      return;
    }

    card.classList.add("has-file");

    const sizeMB = file.size / (1024 * 1024);

    if (copy) {
      copy.textContent = file.name;
    }

    if (sub) {
      sub.textContent =
        `${sizeMB.toFixed(2)} MB · ${file.type || "image"} · ${file.name}`;
    }

    if (browse) {
      browse.innerHTML = 'FILE READY <span>✓</span>';
    }

    /*
     * Show the ACTUAL selected image inside the upload panel.
     */
    if (!preview) {
      preview = document.createElement("img");
      preview.className = "lm-live-preview";
      preview.alt =
        input.name === "image_a"
          ? "Selected Image A preview"
          : "Selected Image B preview";

      /*
       * Put the preview into the visual area. We keep the existing
       * upload-card structure untouched.
       */
      if (emptyVisual) {
        emptyVisual.parentNode.insertBefore(preview, emptyVisual);
        emptyVisual.style.display = "none";
      } else {
        card.insertBefore(preview, card.firstChild);
      }
    }

    const oldURL = preview.dataset.objectUrl;
    if (oldURL) {
      URL.revokeObjectURL(oldURL);
    }

    const objectURL = URL.createObjectURL(file);
    preview.dataset.objectUrl = objectURL;
    preview.src = objectURL;
  }

  inputs.forEach(input => {
    input.addEventListener("change", () => {
      updateFileState(input);
      if (message) message.textContent = "";
    });

    /*
     * Restores the preview if this page is revisited by the
     * smooth-navigation system and the input still contains a file.
     */
    updateFileState(input);
  });

  form.addEventListener("submit", async event => {
    event.preventDefault();

    const imageA = form.querySelector('input[name="image_a"]');
    const imageB = form.querySelector('input[name="image_b"]');

    if (!imageA?.files?.length || !imageB?.files?.length) {
      if (message) {
        message.textContent = "Please select both Image A and Image B.";
      }
      return;
    }

    const fileA = imageA.files[0];
    const fileB = imageB.files[0];
    const maxSize = 25 * 1024 * 1024;

    if (fileA.size > maxSize || fileB.size > maxSize) {
      if (message) {
        message.textContent = "Each image must be 25 MB or smaller.";
      }
      return;
    }

    if (
      !fileA.type.startsWith("image/") ||
      !fileB.type.startsWith("image/")
    ) {
      if (message) {
        message.textContent = "Please select valid image files.";
      }
      return;
    }

    const originalHTML = button ? button.innerHTML : "";

    if (button) {
      button.disabled = true;
      button.classList.add("is-processing");
      button.innerHTML =
        '<span class="lm-run-icon">◌</span>' +
        '<span>ANALYZING OBSERVATIONS…</span>';
    }

    if (message) {
      message.textContent =
        "Uploading observations and starting correspondence analysis…";
    }

    try {
      const formData = new FormData(form);

      const response = await fetch("/api/analyze", {
        method: "POST",
        body: formData
      });

      let data;

      try {
        data = await response.json();
      } catch {
        throw new Error(
          "The analysis server returned an invalid response."
        );
      }

      if (!response.ok) {
        throw new Error(data.error || "Analysis request failed.");
      }

      sessionStorage.setItem("lm_result", JSON.stringify(data));

      if (message) {
        message.textContent =
          "Analysis complete. Opening evidence report…";
      }

      window.location.href = "/results";

    } catch (error) {
      console.error("LUNARMATCH analysis error:", error);

      if (message) {
        message.textContent =
          error.message || "Unable to complete the analysis.";
      }

      if (button) {
        button.disabled = false;
        button.classList.remove("is-processing");
        button.innerHTML = originalHTML;
      }
    }
  });
}

/* =========================================================
   RESULTS PAGE
   Reads BOTH the new V1 backend structure and old results.
   ========================================================= */
function renderResult() {
  const box = document.querySelector("#result");
  if (!box) return;

  const raw = sessionStorage.getItem("lm_result");
  let result = null;

  try {
    result = raw ? JSON.parse(raw) : null;
  } catch (error) {
    console.error("LUNARMATCH result parse error:", error);
  }

  if (!result) {
    box.innerHTML = `
      <div class="card">
        <h3>No recent analysis</h3>
        <p class="muted">Run an analysis first.</p>
      </div>
    `;
    return;
  }

  const corr = result.correspondence || {};
  const geo = result.geometric_verification || {};
  const pipeline = result.pipeline || {};
  const imageA = result.image_a || result.imageA || {};
  const imageB = result.image_b || result.imageB || {};
  const algorithm = result.algorithm || {};
  const instrument = result.instrument_awareness || {};

  const finiteNumber = value => {
    if (typeof value === "number" && Number.isFinite(value)) return value;
    if (typeof value === "string" && value.trim() !== "") {
      const n = Number(value);
      return Number.isFinite(n) ? n : null;
    }
    return null;
  };

  const numberOr = (value, fallback = null) => {
    const n = finiteNumber(value);
    return n === null ? fallback : n;
  };

  const textOr = (value, fallback = "Not available") => {
    if (value === null || value === undefined || value === "") return fallback;
    if (typeof value === "object") return fallback;
    return String(value);
  };

  const statusValue = value => {
    if (value && typeof value === "object" && "value" in value) {
      return textOr(value.value);
    }
    return textOr(value);
  };

  const objectStatus = value => {
    if (value && typeof value === "object") {
      if (value.status) return String(value.status);
      if (value.value !== undefined) return textOr(value.value);
    }
    return textOr(value);
  };

  const qualityObject = image => {
    const q = image.quality || {};
    const qualityScore = numberOr(
      q.quality_score,
      numberOr(q.quality, null)
    );
    const contrast = numberOr(q.contrast, null);
    const sharpness = numberOr(
      q.sharpness_laplacian_variance,
      numberOr(q.sharpness, null)
    );

    return {qualityScore, contrast, sharpness};
  };

  const qa = qualityObject(imageA);
  const qb = qualityObject(imageB);

  const avgQuality = numberOr(
    result.image_quality,
    qa.qualityScore !== null && qb.qualityScore !== null
      ? (qa.qualityScore + qb.qualityScore) / 2
      : null
  );

  const score = numberOr(result.overall_match, numberOr(result.score, 0));
  const verified = numberOr(
    corr.verified_matches,
    numberOr(result.verified_matches, 0)
  );
  const reliability = textOr(
    result.reliability,
    textOr(result.confidence, "INSUFFICIENT")
  );
  const confidenceValue = numberOr(
    result.confidence_detail?.value,
    null
  );
  const inlierRatio = numberOr(
    geo.inlier_ratio_percent,
    numberOr(result.inlier_ratio, 0)
  );

  const stageValue = (...keys) => {
    for (const key of keys) {
      if (key in pipeline && pipeline[key] !== null && pipeline[key] !== undefined) {
        return numberOr(pipeline[key], null);
      }
    }
    return null;
  };

  const pipeRows = [
    ["01 ACQUIRE", stageValue("01_ACQUIRE", "acquire_ms", "acquire")],
    ["02 PREPROCESS", stageValue("02_PREPROCESS", "preprocess_ms", "preprocess")],
    ["03 EXTRACT", stageValue("03_EXTRACT", "extract_ms", "extract")],
    ["04 MATCH", stageValue("04_MATCH", "match_ms", "match")],
    ["05 VERIFY", stageValue("05_VERIFY", "verify_ms", "verify")],
    ["06 SCORE", stageValue("06_SCORE", "score_ms", "score")],
    ["07 REPORT", stageValue("07_REPORT", "report_ms", "report")]
  ];

  const totalPipeline = numberOr(
    pipeline.total_ms,
    numberOr(result.processing_time_ms, null)
  );

  const metadataTable = (metadata, instrumentInfo = {}) => {
    const data = metadata || {};
    const embeddedAvailable = data.available === true;
    const instrumentName =
      statusValue(data.instrument) !== "Not available"
        ? statusValue(data.instrument)
        : textOr(instrumentInfo.instrument, "Not established");

    return `
      <table class="table">
        <tr><th>Metadata status</th><td>${embeddedAvailable ? "AVAILABLE" : "NOT AVAILABLE"}</td></tr>
        <tr><th>Latitude</th><td>${statusValue(data.latitude)}</td></tr>
        <tr><th>Longitude</th><td>${statusValue(data.longitude)}</td></tr>
        <tr><th>Altitude</th><td>${statusValue(data.altitude)}</td></tr>
        <tr><th>Acquisition time</th><td>${statusValue(data.acquisition_time)}</td></tr>
        <tr><th>Mission</th><td>${statusValue(data.mission)}</td></tr>
        <tr><th>Instrument</th><td>${instrumentName}</td></tr>
        <tr><th>CRS</th><td>${statusValue(data.crs)}</td></tr>
        <tr><th>Projection</th><td>${statusValue(data.projection)}</td></tr>
        <tr><th>Datum</th><td>${statusValue(data.datum)}</td></tr>
        <tr><th>Image / Product ID</th><td>${statusValue(data.image_id)} / ${statusValue(data.product_id)}</td></tr>
        <tr><th>Provenance</th><td>${statusValue(data.provenance)}</td></tr>
      </table>
    `;
  };

  const imageTable = (image, quality) => `
    <table class="table">
      <tr><th>Filename</th><td>${textOr(image.filename)}</td></tr>
      <tr><th>Resolution</th><td>${textOr(image.resolution, `${textOr(image.width, "?")} × ${textOr(image.height, "?")}`)}</td></tr>
      <tr><th>Format</th><td>${textOr(image.format)}</td></tr>
      <tr><th>File size</th><td>${image.file_size_mb !== undefined ? `${numberOr(image.file_size_mb, 0)} MB` : "Not available"}</td></tr>
      <tr><th>Channels</th><td>${textOr(image.channels)}</td></tr>
      <tr><th>Color / grayscale</th><td>${textOr(image.color_mode)}</td></tr>
      <tr><th>Keypoints</th><td>${numberOr(image.keypoints, 0)}</td></tr>
      <tr><th>Feature density</th><td>${image.feature_density_per_mp !== undefined ? `${numberOr(image.feature_density_per_mp, 0)} / MP` : "Not available"}</td></tr>
      <tr><th>Processing resolution</th><td>${textOr(image.processing_resolution)}</td></tr>
      <tr><th>Contrast</th><td>${quality.contrast !== null ? quality.contrast : "Not available"}</td></tr>
      <tr><th>Sharpness</th><td>${quality.sharpness !== null ? quality.sharpness : "Not available"}</td></tr>
      <tr><th>Quality score</th><td>${quality.qualityScore !== null ? `${quality.qualityScore} / 100` : "Not available"}</td></tr>
    </table>
  `;

  const spatial = corr.spatial_distribution || geo.spatial_coverage || {};
  const duplicate = corr.duplicate_match_detection || result.duplicate_match_detection || {};
  const transform = geo.transformation_quality || result.transformation_quality || {};

  const interpretationPoints = Array.isArray(result.interpretation?.points)
    ? result.interpretation.points
    : [];

  const interpretationFallback =
    typeof result.interpretation === "string"
      ? result.interpretation
      : "Image correspondence is evidence of visual/geometric similarity; it is not, by itself, geographic ground truth.";

  const ransacText = textOr(
    geo.ransac,
    verified >= 3 ? "EXECUTED" : "NOT EXECUTED"
  );

  const modelText = textOr(
    geo.model,
    textOr(algorithm.geometric_model, "Not established")
  );

  const visualization = result.result_image
    ? `
      <img class="imgresult" src="${result.result_image}" alt="Lunar correspondence visualization">
    `
    : `<p class="muted">No correspondence visualization was generated.</p>`;

  const pdfLink = result.analysis_id
    ? `/api/report/${encodeURIComponent(result.analysis_id)}`
    : "#";

  box.innerHTML = `
    <div class="metrics">
      <div class="card metric">
        <span class="muted">OVERALL MATCH</span>
        <strong>${score.toFixed(2)}%</strong>
      </div>
      <div class="card metric">
        <span class="muted">VERIFIED</span>
        <strong>${verified}</strong>
      </div>
      <div class="card metric">
        <span class="muted">CONFIDENCE</span>
        <strong>${reliability}</strong>
      </div>
      <div class="card metric">
        <span class="muted">IMAGE QUALITY</span>
        <strong>${avgQuality !== null ? `${avgQuality.toFixed(2)}%` : "Not available"}</strong>
      </div>
      <div class="card metric">
        <span class="muted">PROCESS TIME</span>
        <strong>${totalPipeline !== null ? `${totalPipeline.toFixed(1)} ms` : "Not available"}</strong>
      </div>
    </div>

    <br>

    <div class="card">
      <h2>${textOr(result.headline, "ANALYSIS COMPLETE — CORRESPONDENCE RESULT READY")}</h2>
      <p class="muted">
        ${confidenceValue !== null ? `Confidence value: <strong>${confidenceValue.toFixed(2)}%</strong> · ` : ""}
        Verification: <strong>${textOr(geo.verification_status, textOr(result.verification_status, "Not established"))}</strong>
      </p>
      <a class="btn primary" href="${pdfLink}" target="_blank" rel="noopener">DOWNLOAD FULL PDF REPORT ↗</a>
    </div>

    <br>

    <div class="card">
      <h2>Correspondence Map</h2>
      ${visualization}
      <p class="muted">${textOr(result.validation_note, "Correspondence evidence only; geographic ground truth is not established by image matching alone.")}</p>
    </div>

    <br>

    <div class="grid">
      <div class="card">
        <h2>Source Image Analysis</h2>
        ${imageTable(imageA, qa)}
      </div>

      <div class="card">
        <h2>Reference Image Analysis</h2>
        ${imageTable(imageB, qb)}
      </div>

      <div class="card">
        <h2>Feature Correspondence</h2>
        <table class="table">
          <tr><th>Raw KNN</th><td>${numberOr(corr.raw_knn_matches, numberOr(result.raw_matches, 0))}</td></tr>
          <tr><th>Lowe-ratio candidates</th><td>${numberOr(corr.lowe_ratio_candidates, numberOr(result.candidate_matches, 0))}</td></tr>
          <tr><th>Reciprocal</th><td>${numberOr(corr.reciprocal_matches, numberOr(result.reciprocal_matches, 0))}</td></tr>
          <tr><th>Verified</th><td>${verified}</td></tr>
          <tr><th>Outliers</th><td>${numberOr(corr.outliers, numberOr(result.outliers, 0))}</td></tr>
          <tr><th>Feature coverage</th><td>${numberOr(corr.feature_coverage_percent, numberOr(result.feature_coverage, null)) ?? "Not available"}%</td></tr>
          <tr><th>Correspondence strength</th><td>${numberOr(corr.correspondence_strength, numberOr(result.correspondence_strength, null)) ?? "Not available"} / 100</td></tr>
          <tr><th>Spatial distribution</th><td>${objectStatus(spatial)}</td></tr>
          <tr><th>Occupied cells</th><td>${spatial.occupied_grid_cells !== undefined ? spatial.occupied_grid_cells : "Not available"} / ${spatial.grid_cells_total !== undefined ? spatial.grid_cells_total : 16}</td></tr>
          <tr><th>Duplicate / degenerate match detection</th><td>${objectStatus(duplicate)}</td></tr>
        </table>
      </div>

      <div class="card">
        <h2>Geometric Verification</h2>
        <table class="table">
          <tr><th>Verification</th><td>${textOr(geo.verification_status, textOr(result.verification_status, "Not established"))}</td></tr>
          <tr><th>Model</th><td>${modelText}</td></tr>
          <tr><th>RANSAC</th><td>${ransacText}</td></tr>
          <tr><th>Inliers</th><td>${numberOr(geo.inliers, verified)}</td></tr>
          <tr><th>Outliers</th><td>${numberOr(geo.outliers, 0)}</td></tr>
          <tr><th>Inlier ratio</th><td>${inlierRatio}%</td></tr>
          <tr><th>Mean reprojection error</th><td>${geo.reprojection_error_mean_px !== null && geo.reprojection_error_mean_px !== undefined ? `${geo.reprojection_error_mean_px} px` : "Not available"}</td></tr>
          <tr><th>Median reprojection error</th><td>${geo.reprojection_error_median_px !== null && geo.reprojection_error_median_px !== undefined ? `${geo.reprojection_error_median_px} px` : "Not available"}</td></tr>
          <tr><th>Maximum reprojection error</th><td>${geo.reprojection_error_max_px !== null && geo.reprojection_error_max_px !== undefined ? `${geo.reprojection_error_max_px} px` : "Not available"}</td></tr>
          <tr><th>Geometric consistency</th><td>${numberOr(result.geometric_consistency, numberOr(geo.inlier_ratio_percent, null)) ?? "Not available"}%</td></tr>
          <tr><th>Transformation quality</th><td>${objectStatus(transform)}</td></tr>
          <tr><th>Degenerate geometry</th><td>${geo.degenerate_geometry === true ? "YES" : geo.degenerate_geometry === false ? "NO" : "Not available"}</td></tr>
          <tr><th>Spatial coverage</th><td>${numberOr(geo.spatial_coverage?.coverage_percent, numberOr(spatial.coverage_percent, null)) ?? "Not available"}%</td></tr>
        </table>
      </div>

      <div class="card">
        <h2>Analysis Pipeline</h2>
        <table class="table">
          <tr><th>Stage</th><th>Time</th></tr>
          ${pipeRows.map(row => `
            <tr>
              <td>${row[0]}</td>
              <td>${row[1] !== null ? `${row[1]} ms` : "Not available"}</td>
            </tr>
          `).join("")}
          <tr><th>TOTAL</th><th>${totalPipeline !== null ? `${totalPipeline} ms` : "Not available"}</th></tr>
        </table>
      </div>

      <div class="card">
        <h2>Source Observation</h2>
        ${metadataTable(imageA.metadata, instrument.image_a || imageA.instrument || {})}
      </div>

      <div class="card">
        <h2>Reference Observation</h2>
        ${metadataTable(imageB.metadata, instrument.image_b || imageB.instrument || {})}
      </div>
    </div>

    <br>

    <div class="card">
      <h2>Evidence Interpretation</h2>
      ${interpretationPoints.length
        ? `<ul>${interpretationPoints.map(point => `<li>${textOr(point, "Not available")}</li>`).join("")}</ul>`
        : `<p class="muted">${interpretationFallback}</p>`}
      <p class="muted">
        <strong>Localization note:</strong>
        Coordinates and instrument metadata are displayed only when supplied by the source imagery or recognized reference metadata.
      </p>
    </div>
  `;
}

/* =========================================================
   STAR-FIELD PARALLAX
   ========================================================= */
function parallax() {
  const back = document.querySelector(".star-layer-a");
  const mid = document.querySelector(".star-layer-b");
  const front = document.querySelector(".star-layer-c");

  if (!back) return;

  let targetX = 0;
  let targetY = 0;
  let currentX = 0;
  let currentY = 0;

  window.addEventListener("pointermove", event => {
    targetX = (event.clientX / window.innerWidth - 0.5) * 2;
    targetY = (event.clientY / window.innerHeight - 0.5) * 2;
  }, {passive: true});

  function frame() {
    currentX += (targetX - currentX) * 0.035;
    currentY += (targetY - currentY) * 0.035;

    back.style.transform =
      `translate3d(${currentX * 5}px, ${currentY * 5}px, 0)`;

    if (mid) {
      mid.style.transform =
        `translate3d(${currentX * 11}px, ${currentY * 11}px, 0)`;
    }

    if (front) {
      front.style.transform =
        `translate3d(${currentX * 18}px, ${currentY * 18}px, 0)`;
    }

    requestAnimationFrame(frame);
  }

  frame();
}

/* =========================================================
   CURSOR GLOW
   ========================================================= */
function cursor() {
  const glow = document.querySelector("#cursor-glow");
  if (!glow) return;

  let targetX = window.innerWidth / 2;
  let targetY = window.innerHeight / 2;
  let currentX = targetX;
  let currentY = targetY;

  window.addEventListener("pointermove", event => {
    targetX = event.clientX;
    targetY = event.clientY;
  }, {passive: true});

  function animate() {
    currentX += (targetX - currentX) * 0.07;
    currentY += (targetY - currentY) * 0.07;

    glow.style.left = currentX + "px";
    glow.style.top = currentY + "px";

    requestAnimationFrame(animate);
  }

  animate();
}

/* =========================================================
   SMOOTH SAME-ORIGIN NAVIGATION
   ========================================================= */
function lmSmoothNavigation() {
  async function loadPage(url, push = true) {
    try {
      const response = await fetch(url, {
        headers: {"X-Requested-With": "XMLHttpRequest"}
      });

      if (!response.ok) {
        window.location.href = url;
        return;
      }

      const html = await response.text();
      const parser = new DOMParser();
      const documentPage = parser.parseFromString(html, "text/html");

      const newContent = documentPage.querySelector("#page-content");
      const currentContent = document.querySelector("#page-content");

      if (!newContent || !currentContent) {
        window.location.href = url;
        return;
      }

      currentContent.innerHTML = newContent.innerHTML;
      document.title = documentPage.title;

      if (push) {
        history.pushState({}, "", url);
      }

      window.scrollTo(0, 0);

      wireAuth();
      wireAnalyze();
      renderResult();
      initProceduralMoon();

      document.querySelectorAll(".reveal").forEach((element, index) => {
        element.style.animationDelay = `${index * 70}ms`;
        element.classList.add("is-visible");
      });

    } catch (error) {
      console.error("LUNARMATCH navigation error:", error);
      window.location.href = url;
    }
  }

  document.addEventListener("click", event => {
    const link = event.target.closest("a[href]");
    if (!link) return;

    const href = link.getAttribute("href");

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

    const url = new URL(href, window.location.origin);

    if (url.origin !== window.location.origin) return;

    event.preventDefault();
    loadPage(url.href);
  });

  window.addEventListener("popstate", () => {
    loadPage(window.location.href, false);
  });
}

/* =========================================================
   MOBILE NAVIGATION
   ========================================================= */
function lmMobileNavigation() {
  const toggle = document.querySelector(".mobile-menu-toggle");
  const menu = document.querySelector("#mobile-navigation");

  if (!toggle || !menu || toggle.dataset.mobileReady === "true") return;

  toggle.dataset.mobileReady = "true";

  function openMenu() {
    toggle.classList.add("is-open");
    menu.classList.add("is-open");
    toggle.setAttribute("aria-expanded", "true");
    toggle.setAttribute("aria-label", "Close navigation");
    menu.setAttribute("aria-hidden", "false");
    document.body.classList.add("mobile-nav-open");
  }

  function closeMenu() {
    toggle.classList.remove("is-open");
    menu.classList.remove("is-open");
    toggle.setAttribute("aria-expanded", "false");
    toggle.setAttribute("aria-label", "Open navigation");
    menu.setAttribute("aria-hidden", "true");
    document.body.classList.remove("mobile-nav-open");
  }

  toggle.addEventListener("click", event => {
    event.preventDefault();
    event.stopPropagation();

    if (menu.classList.contains("is-open")) {
      closeMenu();
    } else {
      openMenu();
    }
  });

  menu.querySelectorAll("a").forEach(link => {
    link.addEventListener("click", closeMenu);
  });

  document.addEventListener("keydown", event => {
    if (event.key === "Escape" && menu.classList.contains("is-open")) {
      closeMenu();
    }
  });
}

/* =========================================================
   PROCEDURAL LUNAR SPHERE
   ========================================================= */
function initProceduralMoon() {
  const canvas = document.getElementById("lunar-surface-canvas");
  if (!canvas || canvas.dataset.ready === "true") return;

  canvas.dataset.ready = "true";

  const context = canvas.getContext("2d");
  const container = canvas.parentElement;

  if (!context || !container) return;

  let width = 0;
  let height = 0;
  let dpr = 1;
  let rotation = 0;

  const craters = [];

  for (let i = 0; i < 95; i++) {
    craters.push({
      longitude: Math.random() * Math.PI * 2,
      latitude: (Math.random() - 0.5) * Math.PI,
      radius: 0.012 + Math.random() * 0.045,
      depth: 0.25 + Math.random() * 0.65
    });
  }

  function resize() {
    const rect = container.getBoundingClientRect();

    const size = Math.max(
      120,
      Math.min(rect.width, rect.height)
    );

    dpr = Math.min(window.devicePixelRatio || 1, 2);

    width = size;
    height = size;

    canvas.width = Math.floor(size * dpr);
    canvas.height = Math.floor(size * dpr);
    canvas.style.width = size + "px";
    canvas.style.height = size + "px";

    context.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  function draw() {
    const size = Math.min(width, height);
    const centerX = size / 2;
    const centerY = size / 2;
    const radius = size * 0.495;

    context.clearRect(0, 0, width, height);

    const sphere = context.createRadialGradient(
      centerX - radius * 0.30,
      centerY - radius * 0.32,
      radius * 0.04,
      centerX,
      centerY,
      radius * 1.05
    );

    sphere.addColorStop(0, "#d8dce1");
    sphere.addColorStop(0.34, "#a1a7ae");
    sphere.addColorStop(0.68, "#666e78");
    sphere.addColorStop(0.88, "#343c47");
    sphere.addColorStop(1, "#0d131c");

    context.beginPath();
    context.arc(centerX, centerY, radius, 0, Math.PI * 2);
    context.fillStyle = sphere;
    context.fill();

    context.save();

    context.beginPath();
    context.arc(centerX, centerY, radius * 0.995, 0, Math.PI * 2);
    context.clip();

    for (const crater of craters) {
      const longitude = crater.longitude + rotation;

      const x = Math.sin(longitude) * Math.cos(crater.latitude);
      const z = Math.cos(longitude) * Math.cos(crater.latitude);

      if (z < -0.05) continue;

      const y = Math.sin(crater.latitude);

      const px = centerX + x * radius * 0.94;
      const py = centerY - y * radius * 0.94;

      const perspective = 0.72 + z * 0.28;
      const craterRadius = radius * crater.radius * perspective;

      const gradient = context.createRadialGradient(
        px - craterRadius * 0.25,
        py - craterRadius * 0.25,
        craterRadius * 0.05,
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
      gradient.addColorStop(1, "rgba(0,0,0,0)");

      context.fillStyle = gradient;
      context.beginPath();
      context.arc(px, py, craterRadius, 0, Math.PI * 2);
      context.fill();

      context.strokeStyle =
        `rgba(220,225,230,${0.08 * crater.depth})`;

      context.lineWidth = Math.max(
        0.5,
        craterRadius * 0.055
      );

      context.beginPath();
      context.arc(
        px - craterRadius * 0.10,
        py - craterRadius * 0.10,
        craterRadius * 0.68,
        0,
        Math.PI * 2
      );
      context.stroke();
    }

    context.restore();

    const grain = context.createRadialGradient(
      centerX - radius * 0.18,
      centerY - radius * 0.20,
      radius * 0.05,
      centerX,
      centerY,
      radius
    );

    grain.addColorStop(0, "rgba(255,255,255,.035)");
    grain.addColorStop(0.55, "rgba(255,255,255,.01)");
    grain.addColorStop(1, "rgba(0,0,0,.08)");

    context.beginPath();
    context.arc(centerX, centerY, radius, 0, Math.PI * 2);
    context.fillStyle = grain;
    context.fill();

    rotation += 0.00075;
    requestAnimationFrame(draw);
  }

  resize();

  window.addEventListener("resize", resize, {passive: true});
  requestAnimationFrame(draw);
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
document.addEventListener("DOMContentLoaded", () => {
  initializeLunarMatch();
  parallax();
  cursor();
  lmSmoothNavigation();

  requestAnimationFrame(() => {
    document.body.classList.add("lm-ready");
  });
});
