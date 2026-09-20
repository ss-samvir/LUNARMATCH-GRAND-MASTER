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
  const box = document.querySelector("#result");

  if (!box) return;

  const raw = sessionStorage.getItem("lm_result");

  let result = null;

  try {
    result = raw ? JSON.parse(raw) : null;
  } catch (error) {
    console.error("LUNARMATCH result parsing error:", error);
    result = null;
  }

  if (!result) {
    box.innerHTML = `
      <section class="lm-result-card">

        <div class="lm-card-head">
          <div>
            <div class="lm-card-kicker">ANALYSIS STATE</div>
            <h2 class="lm-card-title">No recent analysis</h2>
          </div>

          <span class="lm-status-pill neutral">
            WAITING FOR INPUT
          </span>
        </div>

        <p class="muted">
          Run a correspondence analysis from the Analysis Lab first.
        </p>

      </section>
    `;

    return;
  }


  /*
   * Safe display helpers.
   */

  const safe = value => {
    if (
      value === undefined ||
      value === null ||
      value === ""
    ) {
      return "NOT AVAILABLE";
    }

    return String(value);
  };


  const number = value => {
    if (
      value === undefined ||
      value === null ||
      value === ""
    ) {
      return "NOT AVAILABLE";
    }

    return value;
  };


  const percent = value => {
    if (
      value === undefined ||
      value === null ||
      value === ""
    ) {
      return "NOT AVAILABLE";
    }

    return `${value}%`;
  };


  const image = result.image_a || {};
  const reference = result.image_b || {};

  const metaA = image.metadata || {};
  const metaB = reference.metadata || {};


  const qualityA =
    image.quality_score ??
    image.quality ??
    null;

  const qualityB =
    reference.quality_score ??
    reference.quality ??
    null;


  const confidence =
    result.confidence ??
    result.reliability ??
    "NOT AVAILABLE";

  const reliability =
    result.reliability ??
    "NOT AVAILABLE";

  const score =
    result.score ??
    null;

  const verified =
    result.verified_matches ??
    null;

  const processing =
    result.processing_time_ms ??
    null;

  const rawMatches =
    result.raw_matches ??
    null;

  const candidateMatches =
    result.candidate_matches ??
    null;

  const reciprocalMatches =
    result.reciprocal_matches ??
    result.mutual_matches ??
    null;

  const inliers =
    result.verified_matches ??
    result.inliers ??
    null;

  const outliers =
    result.outliers ??
    (
      inliers !== null &&
      inliers !== undefined &&
      candidateMatches !== null &&
      candidateMatches !== undefined
        ? Math.max(
            0,
            Number(candidateMatches) -
            Number(inliers)
          )
        : null
    );

  const correspondenceStrength =
    result.correspondence_strength ??
    result.match_strength ??
    null;

  const featureCoverage =
    result.feature_coverage ??
    null;

  const spatialCoverage =
    result.spatial_coverage ??
    null;

  const inlierRatio =
    result.inlier_ratio ??
    null;

  const geometricConsistency =
    result.geometric_consistency ??
    null;

  const reprojectionError =
    result.reprojection_error ??
    result.reprojection_error_mean ??
    result.reprojection_error_median ??
    null;

  const homographyStatus =
    result.homography_status ??
    "NOT AVAILABLE";

  const verificationStatus =
    result.verification_status ??
    "NOT AVAILABLE";

  const transformationQuality =
    result.transformation_quality ??
    "NOT AVAILABLE";

  const duplicateDetection =
    result.duplicate_match_detection ??
    "NOT AVAILABLE";

  const degeneracy =
    result.degenerate_geometry ??
    result.degeneracy_status ??
    "NOT AVAILABLE";


  /*
   * Metadata row helper.
   */

  const row = (label, value) => `
    <div class="lm-data-row">
      <span class="lm-data-label">${label}</span>
      <span class="lm-data-value">${safe(value)}</span>
    </div>
  `;


  /*
   * Image information.
   */

  const imagePanel = (
    title,
    tag,
    data
  ) => {
    const metadata =
      data.metadata || {};

    return `
      <div class="lm-image-panel">

        <div class="lm-image-panel-head">

          <strong>${title}</strong>

          <span class="lm-image-tag">
            ${tag}
          </span>

        </div>

        <div class="lm-data-list">

          ${row(
            "Resolution",
            data.resolution ??
            (
              data.width &&
              data.height
                ? `${data.width} × ${data.height}`
                : null
            )
          )}

          ${row(
            "Format",
            data.format ??
            data.file_format
          )}

          ${row(
            "File size",
            data.file_size ??
            data.size_bytes
          )}

          ${row(
            "Channels",
            data.channels ??
            data.channel_count
          )}

          ${row(
            "Color / grayscale",
            data.color_mode ??
            data.mode
          )}

          ${row(
            "Keypoints",
            data.keypoints
          )}

          ${row(
            "Feature density",
            data.feature_density
          )}

          ${row(
            "Contrast",
            data.contrast
          )}

          ${row(
            "Sharpness",
            data.sharpness
          )}

          ${row(
            "Quality score",
            data.quality_score ??
            data.quality
          )}

          ${row(
            "Processing resolution",
            data.processing_resolution
          )}

          ${row(
            "EXIF / metadata",
            metadata &&
            Object.keys(metadata).length
              ? "AVAILABLE"
              : "NOT AVAILABLE"
          )}

        </div>

      </div>
    `;
  };


  /*
   * Metadata panel.
   */

  const metadataPanel = (
    title,
    data
  ) => {

    data = data || {};

    return `
      <div class="lm-result-card">

        <div class="lm-card-head">

          <div>
            <div class="lm-card-kicker">
              OBSERVATION RECORD
            </div>

            <h2 class="lm-card-title">
              ${title}
            </h2>
          </div>

          <span class="lm-status-pill neutral">
            METADATA
          </span>

        </div>

        <div class="lm-data-list">

          ${row(
            "Latitude",
            data.latitude
          )}

          ${row(
            "Longitude",
            data.longitude
          )}

          ${row(
            "Altitude",
            data.altitude
          )}

          ${row(
            "Acquisition time",
            data.acquisition_time
          )}

          ${row(
            "Mission",
            data.mission
          )}

          ${row(
            "Instrument",
            data.instrument ??
            data.camera
          )}

          ${row(
            "CRS",
            data.crs
          )}

          ${row(
            "Projection",
            data.projection
          )}

          ${row(
            "Datum",
            data.datum
          )}

          ${row(
            "Image / Product ID",
            data.image_id ??
            data.product_id
          )}

          ${row(
            "Provenance",
            data.provenance
          )}

        </div>

      </div>
    `;
  };


  /*
   * Interpretation.
   *
   * This is deliberately based only on measured fields.
   */

  let interpretation =
    result.interpretation ??
    result.validation_note ??
    null;

  if (!interpretation) {
    if (
      verified !== null &&
      verified !== undefined &&
      Number(verified) > 0
    ) {
      interpretation =
        `The analysis identified ${verified} geometrically verified correspondence feature${Number(verified) === 1 ? "" : "s"}. ` +
        `Geometric verification status: ${safe(verificationStatus)}. ` +
        `This result represents image correspondence evidence and does not by itself establish geographic ground truth.`;

    } else {
      interpretation =
        `No geometrically verified correspondence was established in this analysis run. ` +
        `The reported result should be interpreted together with the matching and verification metrics.`;
    }
  }


  /*
   * Pipeline status.
   */

  const pipeline = [
    [
      "01",
      "ACQUIRE",
      result.acquire_time_ms
    ],
    [
      "02",
      "PREPROCESS",
      result.preprocess_time_ms
    ],
    [
      "03",
      "EXTRACT",
      result.extract_time_ms ??
      result.feature_extraction_time_ms
    ],
    [
      "04",
      "MATCH",
      result.match_time_ms
    ],
    [
      "05",
      "VERIFY",
      result.verify_time_ms
    ],
    [
      "06",
      "SCORE",
      result.score_time_ms
    ],
    [
      "07",
      "REPORT",
      result.report_time_ms
    ]
  ];


  const pipelineHTML =
    pipeline.map(stage => `
      <div class="lm-pipeline-step">

        <div class="lm-pipeline-num">
          ${stage[0]}
        </div>

        <div class="lm-pipeline-name">
          ${stage[1]}
        </div>

        <div class="lm-pipeline-time">
          ${
            stage[2] !== undefined &&
            stage[2] !== null
              ? `${stage[2]} ms`
              : "NOT AVAILABLE"
          }
        </div>

      </div>
    `).join("");


  /*
   * Result visualization.
   */

  const visualHTML =
    result.result_image
      ? `
        <div class="lm-correspondence-visual">

          <img
            src="${safe(result.result_image)}"
            alt="LunarMatch correspondence visualization"
          >

        </div>
      `
      : `
        <div class="lm-correspondence-visual">

          <div class="lm-visual-empty">

            <strong>
              CORRESPONDENCE VISUALIZATION UNAVAILABLE
            </strong>

            No generated visualization was supplied by
            this analysis run.

          </div>

        </div>
      `;


  /*
   * Report link.
   */

  const analysisId =
    result.analysis_id ??
    result.id ??
    null;

  const reportHTML =
    analysisId
      ? `
        <a
          class="lm-report-button"
          href="/api/report/${encodeURIComponent(analysisId)}"
          target="_blank"
          rel="noopener"
        >
          ↓ DOWNLOAD FULL PDF REPORT
        </a>
      `
      : `
        <span class="lm-report-button"
          style="opacity:.45;cursor:not-allowed;">
          PDF REPORT NOT AVAILABLE
        </span>
      `;


  /*
   * FINAL RESULT UI
   */

  box.innerHTML = `

    <!-- OVERALL RESULT -->

    <section class="lm-result-card reveal">

      <div class="lm-card-head">

        <div>

          <div class="lm-card-kicker">
            ANALYSIS COMPLETE
          </div>

          <h2 class="lm-card-title">
            Correspondence result ready
          </h2>

        </div>

        <span class="lm-status-pill ${
          String(confidence).toLowerCase().includes("insufficient")
            ? "warning"
            : ""
        }">

          ${safe(confidence)}

        </span>

      </div>


      <div class="lm-result-hero-grid">

        <div class="lm-result-main-metric">

          <span class="lm-metric-label">
            OVERALL MATCH
          </span>

          <strong class="lm-main-number">
            ${score !== null ? `${score}%` : "NOT AVAILABLE"}
          </strong>

          <div class="lm-main-caption">
            Evidence score reported by the current analysis engine.
          </div>

        </div>


        <div class="lm-result-small-metric">

          <span class="lm-metric-label">
            VERIFIED
          </span>

          <strong class="lm-small-number">
            ${number(verified)}
          </strong>

          <div class="lm-small-caption">
            Geometric inliers
          </div>

        </div>


        <div class="lm-result-small-metric">

          <span class="lm-metric-label">
            CONFIDENCE
          </span>

          <strong class="lm-small-number">
            ${safe(confidence)}
          </strong>

          <div class="lm-small-caption">
            Reported reliability
          </div>

        </div>


        <div class="lm-result-small-metric">

          <span class="lm-metric-label">
            IMAGE QUALITY
          </span>

          <strong class="lm-small-number">
            ${
              qualityA !== null &&
              qualityB !== null
                ? `${(
                    (
                      Number(qualityA) +
                      Number(qualityB)
                    ) / 2
                  ).toFixed(1)}`
                : "NOT AVAILABLE"
            }
          </strong>

          <div class="lm-small-caption">
            Combined A/B quality
          </div>

        </div>


        <div class="lm-result-small-metric">

          <span class="lm-metric-label">
            PROCESS TIME
          </span>

          <strong class="lm-small-number">
            ${
              processing !== null
                ? `${processing} ms`
                : "NOT AVAILABLE"
            }
          </strong>

          <div class="lm-small-caption">
            Total measured processing
          </div>

        </div>

      </div>

    </section>


    <!-- IMAGE ANALYSIS -->

    <section class="lm-result-card reveal">

      <div class="lm-card-head">

        <div>

          <div class="lm-card-kicker">
            INPUT CHARACTERIZATION
          </div>

          <h2 class="lm-card-title">
            Image analysis
          </h2>

        </div>

        <span class="lm-status-pill neutral">
          A / B
        </span>

      </div>


      <div class="lm-image-grid">

        ${imagePanel(
          "Source Image A",
          "SOURCE",
          image
        )}

        ${imagePanel(
          "Reference Image B",
          "REFERENCE",
          reference
        )}

      </div>

    </section>


    <!-- CORRESPONDENCE -->

    <section class="lm-result-card reveal">

      <div class="lm-card-head">

        <div>

          <div class="lm-card-kicker">
            FEATURE CORRESPONDENCE
          </div>

          <h2 class="lm-card-title">
            Matching evidence
          </h2>

        </div>

        <span class="lm-status-pill neutral">
          CORRESPONDENCE
        </span>

      </div>


      <div class="lm-stat-grid">

        <div class="lm-stat">
          <span class="lm-stat-label">Raw KNN</span>
          <strong class="lm-stat-value">
            ${number(rawMatches)}
          </strong>
        </div>

        <div class="lm-stat">
          <span class="lm-stat-label">Lowe candidates</span>
          <strong class="lm-stat-value">
            ${number(candidateMatches)}
          </strong>
        </div>

        <div class="lm-stat">
          <span class="lm-stat-label">Reciprocal</span>
          <strong class="lm-stat-value">
            ${number(reciprocalMatches)}
          </strong>
        </div>

        <div class="lm-stat">
          <span class="lm-stat-label">Verified</span>
          <strong class="lm-stat-value">
            ${number(inliers)}
          </strong>
        </div>

        <div class="lm-stat">
          <span class="lm-stat-label">Outliers</span>
          <strong class="lm-stat-value">
            ${number(outliers)}
          </strong>
        </div>

        <div class="lm-stat">
          <span class="lm-stat-label">Feature coverage</span>
          <strong class="lm-stat-value">
            ${percent(featureCoverage)}
          </strong>
        </div>

        <div class="lm-stat">
          <span class="lm-stat-label">Spatial coverage</span>
          <strong class="lm-stat-value">
            ${percent(spatialCoverage)}
          </strong>
        </div>

        <div class="lm-stat">
          <span class="lm-stat-label">Correspondence strength</span>
          <strong class="lm-stat-value">
            ${safe(correspondenceStrength)}
          </strong>
        </div>

      </div>

    </section>


    <!-- GEOMETRY -->

    <section class="lm-result-card reveal">

      <div class="lm-card-head">

        <div>

          <div class="lm-card-kicker">
            GEOMETRIC VERIFICATION
          </div>

          <h2 class="lm-card-title">
            Does the geometry agree?
          </h2>

        </div>

        <span class="lm-status-pill ${
          String(verificationStatus)
            .toLowerCase()
            .includes("not")
            ? "warning"
            : ""
        }">

          ${safe(verificationStatus)}

        </span>

      </div>


      <div class="lm-stat-grid">

        <div class="lm-stat">
          <span class="lm-stat-label">Inlier ratio</span>
          <strong class="lm-stat-value">
            ${percent(inlierRatio)}
          </strong>
        </div>

        <div class="lm-stat">
          <span class="lm-stat-label">Geometric consistency</span>
          <strong class="lm-stat-value">
            ${percent(geometricConsistency)}
          </strong>
        </div>

        <div class="lm-stat">
          <span class="lm-stat-label">RANSAC</span>
          <strong class="lm-stat-value">
            ${safe(result.ransac_status)}
          </strong>
        </div>

        <div class="lm-stat">
          <span class="lm-stat-label">Homography</span>
          <strong class="lm-stat-value">
            ${safe(homographyStatus)}
          </strong>
        </div>

        <div class="lm-stat">
          <span class="lm-stat-label">Reprojection error</span>
          <strong class="lm-stat-value">
            ${safe(reprojectionError)}
          </strong>
        </div>

        <div class="lm-stat">
          <span class="lm-stat-label">Transformation</span>
          <strong class="lm-stat-value">
            ${safe(transformationQuality)}
          </strong>
        </div>

        <div class="lm-stat">
          <span class="lm-stat-label">Spatial coverage</span>
          <strong class="lm-stat-value">
            ${percent(spatialCoverage)}
          </strong>
        </div>

        <div class="lm-stat">
          <span class="lm-stat-label">Degeneracy</span>
          <strong class="lm-stat-value">
            ${safe(degeneracy)}
          </strong>
        </div>

      </div>


      <div style="margin-top:18px">

        ${row(
          "Duplicate / degenerate match detection",
          duplicateDetection
        )}

      </div>

    </section>


    <!-- PIPELINE -->

    <section class="lm-result-card reveal">

      <div class="lm-card-head">

        <div>

          <div class="lm-card-kicker">
            PROCESS TRACE
          </div>

          <h2 class="lm-card-title">
            Analysis pipeline
          </h2>

        </div>

        <span class="lm-status-pill neutral">
          07 STAGES
        </span>

      </div>


      <div class="lm-pipeline">
        ${pipelineHTML}
      </div>

    </section>


    <!-- CORRESPONDENCE MAP -->

    <section class="lm-result-card reveal">

      <div class="lm-card-head">

        <div>

          <div class="lm-card-kicker">
            VISUAL EVIDENCE
          </div>

          <h2 class="lm-card-title">
            Feature correspondence map
          </h2>

        </div>

        <span class="lm-status-pill neutral">
          GENERATED OUTPUT
        </span>

      </div>


      ${visualHTML}

    </section>


    <!-- METADATA -->

    <div class="lm-two-column">

      ${metadataPanel(
        "Source observation",
        metaA
      )}

      ${metadataPanel(
        "Reference observation",
        metaB
      )}

    </div>


    <!-- INTERPRETATION -->

    <section class="lm-result-card reveal">

      <div class="lm-card-head">

        <div>

          <div class="lm-card-kicker">
            AUTOMATED ANALYSIS
          </div>

          <h2 class="lm-card-title">
            Evidence interpretation
          </h2>

        </div>

        <span class="lm-status-pill neutral">
          MEASURED DATA
        </span>

      </div>


      <div class="lm-interpretation">

        <p>
          ${safe(interpretation)}
        </p>

      </div>

    </section>


    <!-- REPORT -->

    <section class="lm-result-card reveal">

      <div class="lm-report-actions">

        <div>

          <h3>
            Complete analysis report
          </h3>

          <p>
            Full machine-readable analysis record and generated report,
            when a report identifier is available.
          </p>

        </div>

        ${reportHTML}

      </div>

    </section>

  `;


  /*
   * Re-trigger reveal animation for dynamically
   * inserted result elements.
   */

  requestAnimationFrame(() => {
    box
      .querySelectorAll(".reveal")
      .forEach(
        (element, index) => {

          element.style.animationDelay =
            `${index * 55}ms`;

          element.classList.add(
            "is-visible"
          );

        }
      );

  });

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

/* =========================================================
   HISTORY / SAVED ANALYSIS WORKSPACE
   ========================================================= */

function wireHistory() {

  const list =
    document.querySelector("#history-list");

  const status =
    document.querySelector("#history-status");

  if (!list || !status) {
    return;
  }

  if (list.dataset.historyReady === "true") {
    return;
  }

  list.dataset.historyReady = "true";

  status.textContent =
    "Loading saved analyses...";

  fetch("/api/history", {
    credentials: "same-origin",
    headers: {
      "X-Requested-With": "XMLHttpRequest"
    }
  })
    .then(async response => {

      let data;

      try {
        data = await response.json();
      } catch {
        throw new Error(
          "Unable to read saved analyses."
        );
      }

      if (!response.ok) {
        throw new Error(
          data.error ||
          "Unable to load history."
        );
      }

      return data;
    })
    .then(data => {

      if (!Array.isArray(data) || data.length === 0) {
        status.textContent =
          "No saved analyses yet.";
        list.innerHTML = "";
        return;
      }

      status.textContent =
        `${data.length} saved analysis${data.length === 1 ? "" : "es"}`;

      list.innerHTML = data.map(item => {

        const score =
          item.score !== null &&
          item.score !== undefined
            ? Number(item.score).toFixed(2) + "%"
            : "NOT AVAILABLE";

        const verified =
          item.verified_matches ??
          0;

        return `
          <article class="history-card">

            <div class="history-card-top">

              <div>
                <span class="history-label">
                  ANALYSIS
                </span>

                <h2>
                  ${item.headline || "ANALYSIS COMPLETE"}
                </h2>
              </div>

              <div class="history-confidence">
                ${item.confidence || "UNKNOWN"}
              </div>

            </div>

            <div class="history-meta">

              <span>Score: ${score}</span>

              <span>Verified: ${verified}</span>

              <span>${item.created_at || ""}</span>

            </div>

            <button
              type="button"
              class="history-open"
              data-analysis-id="${item.analysis_id}"
            >
              OPEN SAVED ANALYSIS
            </button>

          </article>
        `;

      }).join("");

      list
        .querySelectorAll(".history-open")
        .forEach(button => {

          button.addEventListener(
            "click",
            async () => {

              const analysisId =
                button.dataset.analysisId;

              if (!analysisId) {
                return;
              }

              button.disabled = true;
              const original =
                button.textContent;

              button.textContent =
                "OPENING…";

              try {

                const response =
                  await fetch(
                    `/api/history/${encodeURIComponent(analysisId)}`,
                    {
                      credentials: "same-origin",
                      headers: {
                        "X-Requested-With":
                          "XMLHttpRequest"
                      }
                    }
                  );

                const result =
                  await response.json();

                if (!response.ok) {
                  throw new Error(
                    result.error ||
                    "Unable to open saved analysis."
                  );
                }

                sessionStorage.setItem(
                  "lm_result",
                  JSON.stringify(result)
                );

                window.location.href =
                  "/results";

              } catch (error) {

                console.error(
                  "LUNARMATCH history error:",
                  error
                );

                button.disabled = false;
                button.textContent =
                  original;

                status.textContent =
                  error.message ||
                  "Unable to open saved analysis.";
              }
            }
          );
        });

    })
    .catch(error => {

      console.error(
        "LUNARMATCH history load error:",
        error
      );

      status.textContent =
        error.message ||
        "Unable to load history.";

      list.innerHTML = "";
    });
}
function initializeLunarMatch() {

  wireAuth();

  wireAnalyze();
   wireHistory();

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
