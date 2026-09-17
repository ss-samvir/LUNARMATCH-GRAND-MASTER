/* ================================================================
   LUNARMATCH V2 — GLOBAL APPLICATION ENGINE
   ---------------------------------------------------------------
   Responsibilities:
   - Authentication forms
   - Image selection + previews
   - Drag & drop
   - Analysis API
   - Pipeline animation
   - Results rendering
   - Validation rendering
   - Stress-lab frontend hooks
   - Safe HTML rendering
   - Session persistence
   ================================================================ */

"use strict";


/* ================================================================
   GLOBAL HELPERS
   ================================================================ */

const LM = {

    /**
     * Safely escape text before inserting backend/user data
     * into HTML.
     */
    escape(value) {

        if (value === null || value === undefined) {
            return "—";
        }

        return String(value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    },


    /**
     * Convert an arbitrary value into a readable display string.
     */
    display(value, fallback = "Not available") {

        if (
            value === null ||
            value === undefined ||
            value === "" ||
            value === "null"
        ) {
            return fallback;
        }

        return LM.escape(value);
    },


    /**
     * POST JSON helper.
     */
    async postJSON(url, data) {

        const response = await fetch(url, {

            method: "POST",

            headers: {
                "Content-Type": "application/json"
            },

            body: JSON.stringify(data)

        });

        let result = {};

        try {
            result = await response.json();
        } catch (error) {
            throw new Error(
                "The server returned an invalid response."
            );
        }

        if (!response.ok) {

            throw new Error(
                result.error ||
                result.message ||
                "Request failed."
            );

        }

        return result;
    },


    /**
     * POST multipart/form-data.
     */
    async postForm(url, formData) {

        const response = await fetch(url, {

            method: "POST",
            body: formData

        });

        let result = {};

        try {
            result = await response.json();
        } catch (error) {

            throw new Error(
                "The server returned an invalid response."
            );

        }

        if (!response.ok) {

            throw new Error(
                result.error ||
                result.message ||
                "Request failed."
            );

        }

        return result;
    },


    /**
     * Safely parse stored analysis data.
     */
    getStoredResult() {

        try {

            const raw =
                sessionStorage.getItem("lm_result");

            if (!raw) {
                return null;
            }

            return JSON.parse(raw);

        } catch (error) {

            console.warn(
                "LunarMatch: stored result could not be read.",
                error
            );

            sessionStorage.removeItem("lm_result");

            return null;
        }
    },


    /**
     * Store latest analysis.
     */
    saveResult(result) {

        try {

            sessionStorage.setItem(
                "lm_result",
                JSON.stringify(result)
            );

        } catch (error) {

            console.warn(
                "LunarMatch: could not store analysis.",
                error
            );

        }

    },


    /**
     * Format numbers without destroying scientific meaning.
     */
    number(value, decimals = 2) {

        if (
            value === null ||
            value === undefined ||
            value === "" ||
            Number.isNaN(Number(value))
        ) {
            return "—";
        }

        return Number(value).toFixed(decimals);
    },


    /**
     * Format a percentage.
     */
    percentage(value) {

        if (
            value === null ||
            value === undefined ||
            value === ""
        ) {
            return "—";
        }

        return `${LM.number(value, 1)}%`;
    },


    /**
     * Return a CSS-safe status class.
     */
    statusClass(status) {

        const value =
            String(status || "")
                .toLowerCase();

        if (
            value.includes("pass") ||
            value.includes("verified") ||
            value.includes("available") ||
            value.includes("established") ||
            value.includes("success") ||
            value.includes("stable")
        ) {
            return "status-good";
        }

        if (
            value.includes("warning") ||
            value.includes("partial") ||
            value.includes("limited") ||
            value.includes("unknown") ||
            value.includes("not established")
        ) {
            return "status-warn";
        }

        if (
            value.includes("fail") ||
            value.includes("error") ||
            value.includes("unavailable")
        ) {
            return "status-bad";
        }

        return "status-neutral";
    },


    /**
     * Change text safely.
     */
    setText(selector, value, fallback = "—") {

        const element =
            document.querySelector(selector);

        if (!element) {
            return;
        }

        element.textContent =
            value === null ||
            value === undefined ||
            value === ""
                ? fallback
                : String(value);
    },


    /**
     * Small delay used for visual pipeline sequencing.
     */
    sleep(milliseconds) {

        return new Promise(resolve =>
            setTimeout(resolve, milliseconds)
        );

    }

};


/* ================================================================
   AUTHENTICATION
   ================================================================ */

function wireAuthForms() {

    const forms =
        document.querySelectorAll(
            "[data-auth]"
        );

    if (!forms.length) {
        return;
    }


    forms.forEach(form => {

        /*
         * Avoid attaching the global handler twice.
         */
        if (form.dataset.authWired === "true") {
            return;
        }

        form.dataset.authWired = "true";


        form.addEventListener(
            "submit",
            async function (event) {

                event.preventDefault();


                const endpoint =
                    form.dataset.auth;

                const message =
                    form.querySelector(
                        "#msg"
                    ) ||
                    document.querySelector(
                        "#msg"
                    );

                const button =
                    form.querySelector(
                        "button[type='submit']"
                    );


                if (message) {

                    message.textContent = "";
                    message.className =
                        "auth-message";

                }


                if (button) {

                    button.disabled = true;

                    if (
                        endpoint.includes("login")
                    ) {

                        button.textContent =
                            "AUTHENTICATING…";

                    } else {

                        button.textContent =
                            "CREATING ACCOUNT…";

                    }

                }


                try {

                    const formData =
                        new FormData(form);

                    const payload = {};


                    formData.forEach(
                        (value, key) => {

                            /*
                             * Do not send files through
                             * authentication forms.
                             */
                            if (
                                typeof value === "string"
                            ) {

                                payload[key] =
                                    value;

                            }

                        }
                    );


                    /*
                     * Password confirmation is a frontend-only
                     * check. The backend only receives the actual
                     * password.
                     */
                    if (
                        payload.confirm_password !==
                        undefined
                    ) {

                        if (
                            payload.password !==
                            payload.confirm_password
                        ) {

                            throw new Error(
                                "Passwords do not match."
                            );

                        }

                        delete payload.confirm_password;

                    }


                    const result =
                        await LM.postJSON(
                            endpoint,
                            payload
                        );


                    if (message) {

                        message.textContent =
                            result.message ||
                            "Operation completed successfully.";

                        message.classList.add(
                            "success"
                        );

                    }


                    /*
                     * Login and registration both lead to
                     * the analysis workspace.
                     */
                    setTimeout(() => {

                        window.location.href =
                            result.redirect ||
                            "/analyze";

                    }, 500);


                } catch (error) {

                    console.error(
                        "Authentication error:",
                        error
                    );


                    if (message) {

                        message.textContent =
                            error.message ||
                            "Authentication failed.";

                        message.classList.add(
                            "error"
                        );

                    }


                    if (button) {

                        button.disabled = false;

                        if (
                            endpoint.includes("login")
                        ) {

                            button.textContent =
                                "SIGN IN →";

                        } else {

                            button.textContent =
                                "CREATE ACCOUNT →";

                        }

                    }

                }

            }
        );

    });

}


/* ================================================================
   IMAGE PREVIEW SYSTEM
   ================================================================ */

function setupImageInput({

    inputId,
    dropId,
    previewId,
    contentId,
    nameId,
    infoId

}) {

    const input =
        document.getElementById(inputId);

    const drop =
        document.getElementById(dropId);

    const preview =
        document.getElementById(previewId);

    const content =
        document.getElementById(contentId);

    const nameElement =
        document.getElementById(nameId);

    const info =
        document.getElementById(infoId);


    if (!input || !drop) {
        return;
    }


    function showFile(file) {

        if (!file) {
            return;
        }


        if (!file.type.startsWith("image/")) {

            if (info) {

                info.innerHTML =
                    "<span>ERROR</span>" +
                    "<small>Please select an image file.</small>";

            }

            return;
        }


        /*
         * Backend limit is 25 MB.
         */
        const maxSize =
            25 * 1024 * 1024;

        if (file.size > maxSize) {

            if (info) {

                info.innerHTML =
                    "<span>FILE TOO LARGE</span>" +
                    "<small>Maximum input size is 25 MB.</small>";

            }

            return;
        }


        /*
         * Put the file into the actual input.
         */
        try {

            const dataTransfer =
                new DataTransfer();

            dataTransfer.items.add(file);

            input.files =
                dataTransfer.files;

        } catch (error) {

            /*
             * Some browsers may restrict programmatic
             * file assignment. The preview still works.
             */
            console.warn(
                "Could not assign dropped file:",
                error
            );

        }


        if (nameElement) {

            nameElement.textContent =
                file.name;

        }


        if (info) {

            const sizeMB =
                file.size /
                (1024 * 1024);

            info.innerHTML =
                `<span>READY</span>
                 <small>${LM.escape(file.name)} · ${sizeMB.toFixed(2)} MB</small>`;

        }


        if (content) {
            content.style.display =
                "none";
        }


        if (preview) {

            const objectURL =
                URL.createObjectURL(file);

            preview.src =
                objectURL;

            preview.style.display =
                "block";

            preview.onload = function () {

                URL.revokeObjectURL(
                    objectURL
                );

            };

        }


        drop.classList.add(
            "has-image"
        );

    }


    input.addEventListener(
        "change",
        function () {

            if (
                input.files &&
                input.files.length
            ) {

                showFile(
                    input.files[0]
                );

            }

        }
    );


    [
        "dragenter",
        "dragover"
    ].forEach(eventName => {

        drop.addEventListener(
            eventName,
            function (event) {

                event.preventDefault();
                event.stopPropagation();

                drop.classList.add(
                    "drag-active"
                );

            }
        );

    });


    [
        "dragleave",
        "drop"
    ].forEach(eventName => {

        drop.addEventListener(
            eventName,
            function (event) {

                event.preventDefault();
                event.stopPropagation();

                drop.classList.remove(
                    "drag-active"
                );

            }
        );

    });


    drop.addEventListener(
        "drop",
        function (event) {

            const files =
                event.dataTransfer.files;

            if (
                files &&
                files.length
            ) {

                showFile(
                    files[0]
                );

            }

        }
    );

}


/* ================================================================
   ANALYSIS INPUTS
   ================================================================ */

function wireAnalysisInputs() {

    setupImageInput({

        inputId: "imageAInput",
        dropId: "dropA",
        previewId: "previewA",
        contentId: "dropContentA",
        nameId: "previewNameA",
        infoId: "fileInfoA"

    });


    setupImageInput({

        inputId: "imageBInput",
        dropId: "dropB",
        previewId: "previewB",
        contentId: "dropContentB",
        nameId: "previewNameB",
        infoId: "fileInfoB"

    });

}


/* ================================================================
   PIPELINE ANIMATION
   ================================================================ */

const PIPELINE_STAGES = [

    "stageAcquire",
    "stagePreprocess",
    "stageExtract",
    "stageMatch",
    "stageVerify",
    "stageScore",
    "stageReport"

];


function resetPipeline() {

    PIPELINE_STAGES.forEach(id => {

        const stage =
            document.getElementById(id);

        if (!stage) {
            return;
        }

        stage.classList.remove(
            "active",
            "complete"
        );

    });


    const status =
        document.querySelector(
            ".pipeline-status"
        );

    if (status) {
        status.textContent =
            "STANDBY";
    }

}


async function animatePipeline() {

    const status =
        document.querySelector(
            ".pipeline-status"
        );


    resetPipeline();


    for (
        let index = 0;
        index < PIPELINE_STAGES.length;
        index++
    ) {

        const current =
            document.getElementById(
                PIPELINE_STAGES[index]
            );

        if (!current) {
            continue;
        }


        current.classList.add(
            "active"
        );


        if (status) {

            const labels = [
                "ACQUIRING",
                "PREPROCESSING",
                "EXTRACTING",
                "MATCHING",
                "VERIFYING",
                "SCORING",
                "REPORTING"
            ];

            status.textContent =
                labels[index] ||
                "PROCESSING";

        }


        await LM.sleep(
            index === 0
                ? 250
                : 350
        );


        current.classList.remove(
            "active"
        );

        current.classList.add(
            "complete"
        );

    }

}


/* ================================================================
   ANALYSIS ENGINE
   ================================================================ */

function wireAnalyze() {

    const button =
        document.getElementById(
            "compareBtn"
        );

    if (!button) {
        return;
    }


    const imageA =
        document.getElementById(
            "imageAInput"
        );

    const imageB =
        document.getElementById(
            "imageBInput"
        );

    const message =
        document.getElementById(
            "analysisMsg"
        );


    button.addEventListener(
        "click",
        async function () {

            if (
                !imageA ||
                !imageB
            ) {
                return;
            }


            if (
                !imageA.files ||
                !imageA.files.length
            ) {

                showAnalysisMessage(
                    "Please select Image A first.",
                    "error"
                );

                return;
            }


            if (
                !imageB.files ||
                !imageB.files.length
            ) {

                showAnalysisMessage(
                    "Please select Image B first.",
                    "error"
                );

                return;
            }


            const formData =
                new FormData();

            formData.append(
                "image_a",
                imageA.files[0]
            );

            formData.append(
                "image_b",
                imageB.files[0]
            );


            button.disabled = true;
            button.classList.add(
                "processing"
            );

            button.innerHTML =
                "<span>RUNNING CORRESPONDENCE ENGINE…</span><b>◌</b>";


            if (message) {

                message.textContent =
                    "Initializing scientific image correspondence analysis…";

                message.className =
                    "analysis-message active";

            }


            /*
             * Run visual animation alongside the actual
             * backend computation.
             */
            animatePipeline();


            try {

                const result =
                    await LM.postForm(
                        "/api/analyze",
                        formData
                    );


                LM.saveResult(
                    result
                );


                /*
                 * Mark pipeline complete.
                 */
                PIPELINE_STAGES.forEach(
                    id => {

                        const stage =
                            document.getElementById(
                                id
                            );

                        if (stage) {

                            stage.classList.remove(
                                "active"
                            );

                            stage.classList.add(
                                "complete"
                            );

                        }

                    }
                );


                const status =
                    document.querySelector(
                        ".pipeline-status"
                    );

                if (status) {
                    status.textContent =
                        "COMPLETE";
                }


                if (message) {

                    message.textContent =
                        "Analysis complete. Opening evidence dashboard…";

                    message.className =
                        "analysis-message success";

                }


                await LM.sleep(450);

                window.location.href =
                    "/results";


            } catch (error) {

                console.error(
                    "Analysis error:",
                    error
                );


                resetPipeline();


                if (message) {

                    message.textContent =
                        error.message ||
                        "Analysis failed.";

                    message.className =
                        "analysis-message error";

                }


                button.disabled = false;
                button.classList.remove(
                    "processing"
                );

                button.innerHTML =
                    "<span>RUN CORRESPONDENCE ENGINE</span><b>→</b>";

            }

        }
    );

}


function showAnalysisMessage(
    text,
    type = ""
) {

    const message =
        document.getElementById(
            "analysisMsg"
        );

    if (!message) {
        return;
    }

    message.textContent =
        text;

    message.className =
        "analysis-message " +
        type;

}


/* ================================================================
   RESULT DATA HELPERS
   ================================================================ */

function getImageResult(result, key) {

    if (!result) {
        return {};
    }

    return result[key] || {};

}


function getMetadata(imageResult) {

    if (
        !imageResult ||
        typeof imageResult !== "object"
    ) {
        return {};
    }

    return imageResult.metadata || {};

}


function metadataTable(metadata) {

    const rows = [

        [
            "Latitude",
            LM.display(
                metadata.latitude
            )
        ],

        [
            "Longitude",
            LM.display(
                metadata.longitude
            )
        ],

        [
            "Altitude",
            LM.display(
                metadata.altitude
            )
        ],

        [
            "Acquisition Time",
            LM.display(
                metadata.acquisition_time
            )
        ],

        [
            "Mission",
            LM.display(
                metadata.mission
            )
        ],

        [
            "Instrument",
            LM.display(
                metadata.camera
            )
        ],

        [
            "Image ID",
            LM.display(
                metadata.image_id
            )
        ],

        [
            "CRS",
            LM.display(
                metadata.crs
            )
        ],

        [
            "Projection",
            LM.display(
                metadata.projection
            )
        ],

        [
            "Datum",
            LM.display(
                metadata.datum
            )
        ],

        [
            "Reference Source",
            LM.display(
                metadata.reference_source
            )
        ]

    ];


    return `
        <table class="table metadata-table">
            <tbody>
                ${rows.map(row => `
                    <tr>
                        <th>${LM.escape(row[0])}</th>
                        <td>${row[1]}</td>
                    </tr>
                `).join("")}
            </tbody>
        </table>
    `;

}


/* ================================================================
   RESULTS DASHBOARD
   ================================================================ */

async function renderResults() {

    const container =
        document.getElementById(
            "result"
        );

    if (!container) {
        return;
    }


    const loading =
        document.getElementById(
            "resultLoading"
        );

    const noResult =
        document.getElementById(
            "noResult"
        );


    let result =
        LM.getStoredResult();


    /*
     * If sessionStorage is empty, attempt to retrieve the
     * latest server-side result.
     */
    if (!result) {

        try {

            const response =
                await fetch(
                    "/api/results"
                );


            if (response.ok) {

                const serverResult =
                    await response.json();

                if (serverResult) {

                    result =
                        serverResult;

                    LM.saveResult(
                        result
                    );

                }

            }

        } catch (error) {

            console.warn(
                "Could not retrieve server result:",
                error
            );

        }

    }


    if (loading) {
        loading.hidden = true;
    }


    if (!result) {

        if (noResult) {
            noResult.hidden = false;
        }

        return;
    }


    if (noResult) {
        noResult.hidden = true;
    }


    container.innerHTML =
        buildResultsHTML(
            result
        );

}


/* ================================================================
   RESULTS HTML
   ================================================================ */

function buildResultsHTML(result) {

    const imageA =
        getImageResult(
            result,
            "image_a"
        );

    const imageB =
        getImageResult(
            result,
            "image_b"
        );


    const metadataA =
        getMetadata(imageA);

    const metadataB =
        getMetadata(imageB);


    const reliability =
        result.reliability ??
        "Not established";


    const score =
        result.score;


    const verified =
        result.verified_matches;


    const inlierRatio =
        result.inlier_ratio;


    const imageURL =
        result.result_image ||
        "";


    const validationNote =
        result.validation_note ||
        "No additional validation note available.";


    return `

        <!-- =====================================================
             TOP METRICS
        ====================================================== -->

        <section class="result-metrics">

            <div class="card metric-card">

                <span class="metric-label">
                    RELIABILITY
                </span>

                <strong>
                    ${LM.escape(reliability)}
                </strong>

                <small>
                    Evidence classification
                </small>

            </div>


            <div class="card metric-card">

                <span class="metric-label">
                    EVIDENCE SCORE
                </span>

                <strong>
                    ${LM.percentage(score)}
                </strong>

                <small>
                    Composite correspondence evidence
                </small>

            </div>


            <div class="card metric-card">

                <span class="metric-label">
                    VERIFIED MATCHES
                </span>

                <strong>
                    ${LM.display(verified)}
                </strong>

                <small>
                    Geometrically consistent
                </small>

            </div>


            <div class="card metric-card">

                <span class="metric-label">
                    INLIER RATIO
                </span>

                <strong>
                    ${LM.percentage(inlierRatio)}
                </strong>

                <small>
                    RANSAC-supported candidates
                </small>

            </div>

        </section>


        <!-- =====================================================
             CORRESPONDENCE VISUAL
        ====================================================== -->

        <section class="card result-visual-card">

            <div class="result-section-head">

                <div>

                    <div class="eyebrow">
                        COMPUTATIONAL EVIDENCE
                    </div>

                    <h2>
                        Correspondence
                        <span class="gradient">
                            map.
                        </span>
                    </h2>

                </div>

                <span class="result-badge">
                    RANSAC VERIFIED
                </span>

            </div>


            ${
                imageURL
                    ? `
                        <div class="result-image-frame">

                            <img
                                class="imgresult"
                                src="${LM.escape(imageURL)}"
                                alt="LunarMatch correspondence visualization"
                            >

                        </div>
                    `
                    : `
                        <div class="empty-visual">
                            Correspondence visualization unavailable.
                        </div>
                    `
            }


            <p class="muted result-note">
                ${LM.escape(validationNote)}
            </p>

        </section>


        <!-- =====================================================
             IMAGE METADATA
        ====================================================== -->

        <section class="result-two-column">

            <div class="card">

                <div class="eyebrow">
                    SOURCE OBSERVATION
                </div>

                <h2>
                    Image A
                </h2>

                <p class="muted result-filename">
                    ${LM.display(
                        imageA.filename,
                        "Source image"
                    )}
                </p>

                ${metadataTable(metadataA)}

            </div>


            <div class="card">

                <div class="eyebrow">
                    REFERENCE OBSERVATION
                </div>

                <h2>
                    Image B
                </h2>

                <p class="muted result-filename">
                    ${LM.display(
                        imageB.filename,
                        "Reference image"
                    )}
                </p>

                ${metadataTable(metadataB)}

            </div>

        </section>


        <!-- =====================================================
             COMPUTATIONAL VERIFICATION
        ====================================================== -->

        <section class="card">

            <div class="eyebrow">
                GEOMETRIC VERIFICATION
            </div>

            <h2>
                How the correspondence
                <span class="gradient">
                    was tested.
                </span>
            </h2>


            <div class="verification-grid">

                ${resultMetric(
                    "Raw Matches",
                    result.raw_matches
                )}

                ${resultMetric(
                    "Candidate Matches",
                    result.candidate_matches
                )}

                ${resultMetric(
                    "Verified Matches",
                    result.verified_matches
                )}

                ${resultMetric(
                    "Inlier Ratio",
                    LM.percentage(
                        result.inlier_ratio
                    )
                )}

                ${resultMetric(
                    "Geometric Consistency",
                    LM.percentage(
                        result.geometric_consistency
                    )
                )}

                ${resultMetric(
                    "Feature Coverage",
                    LM.percentage(
                        result.feature_coverage
                    )
                )}

                ${resultMetric(
                    "Homography",
                    result.homography_status
                )}

                ${resultMetric(
                    "Processing Time",
                    result.processing_time_ms !==
                    undefined
                        ? `${LM.number(
                            result.processing_time_ms,
                            1
                        )} ms`
                        : "Not available"
                )}

            </div>

        </section>


        <!-- =====================================================
             SCIENTIFIC VALIDATION SUMMARY
        ====================================================== -->

        <section class="card">

            <div class="eyebrow">
                SCIENTIFIC VALIDATION
            </div>

            <h2>
                Evidence
                <span class="gradient">
                    layers.
                </span>
            </h2>

            ${buildValidationSummary(result)}

        </section>


        <!-- =====================================================
             ACTIONS
        ====================================================== -->

        <section class="result-actions">

            <a
                href="/validation"
                class="btn primary">

                OPEN VALIDATION CENTER →

            </a>


            <a
                href="/stress"
                class="btn">

                TEST ROBUSTNESS →

            </a>


            <a
                href="/analyze"
                class="btn">

                NEW ANALYSIS

            </a>

        </section>

    `;

}


function resultMetric(
    label,
    value
) {

    return `

        <div class="verification-item">

            <span>
                ${LM.escape(label)}
            </span>

            <strong>
                ${LM.display(value)}
            </strong>

        </div>

    `;

}


/* ================================================================
   VALIDATION SUMMARY
   ================================================================ */

function buildValidationSummary(result) {

    const validation =
        result.validation ||
        {};


    const instrument =
        validation.instrument ||
        {};


    const coordinates =
        validation.coordinate_validation ||
        {};


    const mission =
        validation.mission_validation ||
        {};


    const projection =
        validation.projection_validation ||
        {};


    const reference =
        validation.reference_validation ||
        {};


    return `

        <div class="validation-summary-grid">

            ${validationSummaryCard(
                "INSTRUMENT",
                instrument.status ||
                instrument.name ||
                "Not established"
            )}

            ${validationSummaryCard(
                "COORDINATES",
                coordinates.status ||
                "Not available"
            )}

            ${validationSummaryCard(
                "MISSION",
                mission.status ||
                "Not established"
            )}

            ${validationSummaryCard(
                "PROJECTION",
                projection.status ||
                "Not established"
            )}

            ${validationSummaryCard(
                "REFERENCE",
                reference.status ||
                "Not established"
            )}

        </div>

    `;

}


function validationSummaryCard(
    label,
    value
) {

    const className =
        LM.statusClass(value);


    return `

        <div
            class="validation-summary-item ${className}">

            <span>
                ${LM.escape(label)}
            </span>

            <strong>
                ${LM.escape(value)}
            </strong>

        </div>

    `;

}


/* ================================================================
   VALIDATION CENTER
   ================================================================ */

function renderValidation() {

    const page =
        document.querySelector(
            ".validation-page"
        );

    if (!page) {
        return;
    }


    const result =
        LM.getStoredResult();


    if (!result) {

        fillValidationEmptyState();

        return;
    }


    const validation =
        result.validation ||
        {};


    const instrument =
        validation.instrument ||
        {};


    const coordinates =
        validation.coordinate_validation ||
        {};


    const mission =
        validation.mission_validation ||
        {};


    const projection =
        validation.projection_validation ||
        {};


    const reference =
        validation.reference_validation ||
        {};


    /*
     * Instrument layer
     */
    updateInstrumentCard(
        "ohrc",
        instrument,
        "OHRC"
    );

    updateInstrumentCard(
        "tmc",
        instrument,
        "TMC"
    );

    updateInstrumentCard(
        "iirs",
        instrument,
        "IIRS"
    );


    /*
     * Coordinate layer
     */
    setValidationValue(
        "locationStatus",
        coordinates.status ||
        "Not available"
    );


    const imageA =
        getImageResult(
            result,
            "image_a"
        );

    const metadataA =
        getMetadata(imageA);


    setValidationValue(
        "validationLatitude",
        metadataA.latitude
    );

    setValidationValue(
        "validationLongitude",
        metadataA.longitude
    );


    setValidationValue(
        "coordinateBasis",
        coordinates.basis ||
        coordinates.source ||
        "Evidence source not established"
    );


    setValidationValue(
        "validationCrs",
        metadataA.crs
    );

    setValidationValue(
        "validationProjection",
        metadataA.projection
    );

    setValidationValue(
        "validationDatum",
        metadataA.datum
    );

    setValidationValue(
        "validationImageId",
        metadataA.image_id
    );


    /*
     * Mission
     */
    setValidationValue(
        "missionValidationStatus",
        mission.status ||
        "Not established"
    );

    setValidationValue(
        "missionValidationText",
        mission.text ||
        mission.message ||
        "No independent mission evidence was established."
    );


    /*
     * Reference
     */
    setValidationValue(
        "referenceValidationStatus",
        reference.status ||
        "Not established"
    );

    setValidationValue(
        "referenceValidationText",
        reference.text ||
        reference.message ||
        "No independent reference evidence was established."
    );


    /*
     * Projection
     */
    setValidationValue(
        "projectionValidationStatus",
        projection.status ||
        "Not established"
    );

    setValidationValue(
        "projectionValidationText",
        projection.text ||
        projection.message ||
        "No projection validation evidence was established."
    );


    /*
     * Warnings
     */
    const warnings =
        Array.isArray(
            validation.warnings
        )
            ? validation.warnings
            : [];


    const warningCount =
        document.getElementById(
            "warningCount"
        );


    const warningBox =
        document.getElementById(
            "validationWarnings"
        );


    if (warningCount) {

        warningCount.textContent =
            String(
                warnings.length
            );

    }


    if (warningBox) {

        if (!warnings.length) {

            warningBox.innerHTML = `
                <div class="validation-clear">
                    <span>✓</span>
                    No validation warnings were returned.
                </div>
            `;

        } else {

            warningBox.innerHTML = `

                <ul class="warning-list">

                    ${warnings.map(
                        warning => `
                            <li>
                                ${LM.escape(
                                    warning
                                )}
                            </li>
                        `
                    ).join("")}

                </ul>

            `;

        }

    }

}


function updateInstrumentCard(
    prefix,
    instrument,
    instrumentName
) {

    const detected =
        String(
            instrument.detected ||
            instrument.name ||
            ""
        ).toUpperCase();


    const isDetected =
        detected.includes(
            instrumentName
        );


    setValidationValue(
        `${prefix}Status`,
        isDetected
            ? "IDENTITY ESTABLISHED"
            : "NOT ESTABLISHED"
    );


    setValidationValue(
        `${prefix}A`,
        isDetected
            ? "Detected in available metadata"
            : "No supporting metadata"
    );


    setValidationValue(
        `${prefix}B`,
        isDetected
            ? "Evidence source available"
            : "Independent evidence required"
    );

}


function setValidationValue(
    id,
    value
) {

    const element =
        document.getElementById(
            id
        );

    if (!element) {
        return;
    }

    element.textContent =
        value === null ||
        value === undefined ||
        value === ""
            ? "Not available"
            : String(value);

}


function fillValidationEmptyState() {

    [
        "locationStatus",
        "validationLatitude",
        "validationLongitude",
        "coordinateBasis",
        "validationCrs",
        "validationProjection",
        "validationDatum",
        "validationImageId",
        "missionValidationStatus",
        "missionValidationText",
        "referenceValidationStatus",
        "referenceValidationText",
        "projectionValidationStatus",
        "projectionValidationText"
    ].forEach(id => {

        setValidationValue(
            id,
            "No analysis available"
        );

    });


    [
        "ohrcStatus",
        "tmcStatus",
        "iirsStatus"
    ].forEach(id => {

        setValidationValue(
            id,
            "NO ANALYSIS"
        );

    });


    const warningBox =
        document.getElementById(
            "validationWarnings"
        );

    if (warningBox) {

        warningBox.innerHTML = `
            <div class="validation-clear">
                Run an analysis first to populate the validation evidence.
            </div>
        `;

    }

}


/* ================================================================
   STRESS LAB
   ================================================================ */

function wireStressLab() {

    const fileInput =
        document.getElementById(
            "stressImage"
        );

    const runButton =
        document.getElementById(
            "stressRunBtn"
        );


    /*
     * The stress page has its own input IDs.
     */
    if (fileInput) {

        setupImageInput({

            inputId: "stressImage",
            dropId: "stressDrop",
            previewId: "stressPreview",
            contentId: "stressDropContent",
            nameId: "stressPreviewName",
            infoId: "stressFileInfo"

        });

    }


    const severity =
        document.getElementById(
            "stressSeverity"
        );

    const severityValue =
        document.getElementById(
            "stressSeverityValue"
        );


    if (severity && severityValue) {

        function updateSeverity() {

            severityValue.textContent =
                severity.value;

            updateStressDescription();

        }


        severity.addEventListener(
            "input",
            updateSeverity
        );


        updateSeverity();

    }


    const stressType =
        document.getElementById(
            "stressType"
        );


    if (stressType) {

        stressType.addEventListener(
            "change",
            updateStressDescription
        );

    }


    if (runButton) {

        runButton.addEventListener(
            "click",
            runStressTest
        );

    }

}


function updateStressDescription() {

    const type =
        document.getElementById(
            "stressType"
        );

    const severity =
        document.getElementById(
            "stressSeverity"
        );

    const description =
        document.getElementById(
            "stressDescription"
        );


    if (
        !type ||
        !severity ||
        !description
    ) {
        return;
    }


    const descriptions = {

        rotation:
            "Tests correspondence stability when the observation is rotated.",

        scale:
            "Tests correspondence stability under controlled scale change.",

        brightness:
            "Tests resilience to illumination / brightness variation.",

        contrast:
            "Tests resilience to contrast variation.",

        noise:
            "Tests robustness against synthetic image noise.",

        blur:
            "Tests robustness when image detail is reduced by blur.",

        crop:
            "Tests correspondence under reduced spatial overlap."

    };


    const selected =
        descriptions[
            type.value
        ] ||
        "Controlled synthetic robustness test.";


    description.textContent =
        selected +
        ` Severity: ${severity.value}.`;

}


async function runStressTest() {

    const fileInput =
        document.getElementById(
            "stressImage"
        );

    const type =
        document.getElementById(
            "stressType"
        );

    const severity =
        document.getElementById(
            "stressSeverity"
        );

    const button =
        document.getElementById(
            "stressRunBtn"
        );

    const message =
        document.getElementById(
            "stressMessage"
        );


    if (
        !fileInput ||
        !fileInput.files ||
        !fileInput.files.length
    ) {

        showStressMessage(
            "Select an image before running the stress test.",
            "error"
        );

        return;
    }


    if (!type || !severity) {
        return;
    }


    const formData =
        new FormData();

    formData.append(
        "image",
        fileInput.files[0]
    );

    formData.append(
        "transform",
        type.value
    );

    formData.append(
        "severity",
        severity.value
    );


    if (button) {

        button.disabled = true;

        button.textContent =
            "RUNNING STRESS TEST…";

    }


    showStressMessage(
        "Generating controlled transformation and measuring correspondence stability…",
        "active"
    );


    try {

        /*
         * This endpoint will be enabled when the stress
         * backend is added.
         */
        const result =
            await LM.postForm(
                "/api/stress",
                formData
            );


        renderStressResult(
            result
        );


        showStressMessage(
            "Stress test complete.",
            "success"
        );


    } catch (error) {

        console.error(
            "Stress test error:",
            error
        );


        showStressMessage(
            error.message ||
            "Stress test failed.",
            "error"
        );


    } finally {

        if (button) {

            button.disabled = false;

            button.textContent =
                "RUN STRESS TEST →";

        }

    }

}


function showStressMessage(
    text,
    type = ""
) {

    const message =
        document.getElementById(
            "stressMessage"
        );

    if (!message) {
        return;
    }

    message.textContent =
        text;

    message.className =
        "stress-message " +
        type;

}


function renderStressResult(result) {

    const empty =
        document.getElementById(
            "stressResultEmpty"
        );

    const output =
        document.getElementById(
            "stressResult"
        );


    if (empty) {
        empty.hidden = true;
    }


    if (!output) {
        return;
    }


    output.hidden = false;


    setValidationValue(
        "stressBaseScore",
        result.base_score !==
        undefined
            ? LM.percentage(
                result.base_score
            )
            : "Not available"
    );


    setValidationValue(
        "stressTestScore",
        result.test_score !==
        undefined
            ? LM.percentage(
                result.test_score
            )
            : "Not available"
    );


    setValidationValue(
        "stressVerified",
        result.verified_matches
    );


    setValidationValue(
        "stressStability",
        result.stability !==
        undefined
            ? LM.percentage(
                result.stability
            )
            : "Not available"
    );


    setValidationValue(
        "stressOutputType",
        result.transform
    );


    setValidationValue(
        "stressOutputSeverity",
        result.severity
    );


    setValidationValue(
        "stressOutputGeometry",
        result.homography_status
    );


    setValidationValue(
        "stressOutputInterpretation",
        result.interpretation
    );


    const basePreview =
        document.getElementById(
            "stressBasePreview"
        );

    const transformedPreview =
        document.getElementById(
            "stressTransformedPreview"
        );


    if (
        basePreview &&
        result.base_image
    ) {

        basePreview.src =
            result.base_image;

    }


    if (
        transformedPreview &&
        result.transformed_image
    ) {

        transformedPreview.src =
            result.transformed_image;

    }


    const status =
        document.getElementById(
            "stressResultStatus"
        );


    if (status) {

        status.textContent =
            result.status ||
            "TEST COMPLETE";

        status.className =
            "stress-result-status " +
            LM.statusClass(
                result.status
            );

    }

}


/* ================================================================
   GLOBAL ACTIVE NAVIGATION
   ================================================================ */

function updateActiveNavigation() {

    const currentPath =
        window.location.pathname
            .replace(/\/+$/, "") ||
        "/";


    const links =
        document.querySelectorAll(
            ".links a"
        );


    links.forEach(link => {

        const href =
            link.getAttribute(
                "href"
            );


        if (!href) {
            return;
        }


        let linkPath =
            href
                .replace(
                    /\/+$/,
                    ""
                ) ||
            "/";


        if (
            linkPath ===
            currentPath
        ) {

            link.classList.add(
                "active"
            );

        } else {

            link.classList.remove(
                "active"
            );

        }

    });

}


/* ================================================================
   MOBILE NAVIGATION
   ================================================================ */

function wireMobileNavigation() {

    const toggle =
        document.getElementById(
            "mobileMenuToggle"
        );

    const menu =
        document.getElementById(
            "mobileMenu"
        );


    if (
        !toggle ||
        !menu
    ) {
        return;
    }


    toggle.addEventListener(
        "click",
        function () {

            const isOpen =
                menu.classList.toggle(
                    "open"
                );


            toggle.classList.toggle(
                "open",
                isOpen
            );


            toggle.setAttribute(
                "aria-expanded",
                String(isOpen)
            );

        }
    );


    menu.querySelectorAll(
        "a"
    ).forEach(link => {

        link.addEventListener(
            "click",
            function () {

                menu.classList.remove(
                    "open"
                );

                toggle.classList.remove(
                    "open"
                );

                toggle.setAttribute(
                    "aria-expanded",
                    "false"
                );

            }
        );

    });

}


/* ================================================================
   PAGE ENTRANCE EFFECTS
   ================================================================ */

function setupRevealEffects() {

    const elements =
        document.querySelectorAll(
            ".card, .principle-card, .pipeline-step-new, .instrument-card"
        );


    if (!elements.length) {
        return;
    }


    /*
     * IntersectionObserver gives the interface a subtle
     * research-console style reveal without requiring
     * external libraries.
     */
    if (
        "IntersectionObserver" in window
    ) {

        const observer =
            new IntersectionObserver(
                entries => {

                    entries.forEach(
                        entry => {

                            if (
                                entry.isIntersecting
                            ) {

                                entry.target.classList.add(
                                    "reveal-visible"
                                );

                                observer.unobserve(
                                    entry.target
                                );

                            }

                        }
                    );

                },
                {
                    threshold: 0.08
                }
            );


        elements.forEach(
            element => {

                element.classList.add(
                    "reveal-ready"
                );

                observer.observe(
                    element
                );

            }
        );

    } else {

        elements.forEach(
            element =>
                element.classList.add(
                    "reveal-visible"
                )
        );

    }

}


/* ================================================================
   RESULT IMAGE LIGHTBOX
   ================================================================ */

function wireResultImage() {

    const container =
        document.getElementById(
            "result"
        );

    if (!container) {
        return;
    }


    container.addEventListener(
        "click",
        function (event) {

            const image =
                event.target.closest(
                    ".imgresult"
                );


            if (!image) {
                return;
            }


            /*
             * Do not open if image is broken.
             */
            if (
                !image.src ||
                image.naturalWidth === 0
            ) {
                return;
            }


            const overlay =
                document.createElement(
                    "div"
                );

            overlay.className =
                "image-lightbox";


            overlay.innerHTML = `

                <button
                    class="lightbox-close"
                    type="button"
                    aria-label="Close image">

                    ×

                </button>

                <img
                    src="${LM.escape(
                        image.src
                    )}"
                    alt="${LM.escape(
                        image.alt ||
                        "Correspondence visualization"
                    )}"
                >

            `;


            document.body.appendChild(
                overlay
            );


            requestAnimationFrame(
                () => {

                    overlay.classList.add(
                        "open"
                    );

                }
            );


            function close() {

                overlay.classList.remove(
                    "open"
                );

                setTimeout(
                    () => {

                        overlay.remove();

                    },
                    200
                );

            }


            overlay.addEventListener(
                "click",
                function (event) {

                    if (
                        event.target ===
                        overlay ||
                        event.target.closest(
                            ".lightbox-close"
                        )
                    ) {

                        close();

                    }

                }
            );


            document.addEventListener(
                "keydown",
                function escapeHandler(event) {

                    if (
                        event.key ===
                        "Escape"
                    ) {

                        close();

                        document.removeEventListener(
                            "keydown",
                            escapeHandler
                        );

                    }

                }
            );

        }
    );

}


/* ================================================================
   HEALTH INDICATOR
   ================================================================ */

async function checkEngineHealth() {

    const indicators =
        document.querySelectorAll(
            "[data-engine-status]"
        );


    if (!indicators.length) {
        return;
    }


    try {

        const response =
            await fetch(
                "/health",
                {
                    cache: "no-store"
                }
            );


        if (!response.ok) {
            throw new Error(
                "Health endpoint unavailable."
            );
        }


        const health =
            await response.json();


        indicators.forEach(
            element => {

                element.textContent =
                    health.status ||
                    "ONLINE";

                element.classList.add(
                    "online"
                );

            }
        );


    } catch (error) {

        console.warn(
            "LunarMatch engine health check failed:",
            error
        );


        indicators.forEach(
            element => {

                element.textContent =
                    "OFFLINE";

                element.classList.add(
                    "offline"
                );

            }
        );

    }

}


/* ================================================================
   GLOBAL KEYBOARD SHORTCUTS
   ================================================================ */

function wireKeyboardShortcuts() {

    document.addEventListener(
        "keydown",
        function (event) {

            /*
             * Ignore shortcuts while typing.
             */
            const tag =
                document.activeElement
                    ?.tagName
                    ?.toLowerCase();


            if (
                tag === "input" ||
                tag === "textarea" ||
                tag === "select"
            ) {
                return;
            }


            /*
             * A → Analysis
             */
            if (
                event.key.toLowerCase() ===
                "a"
            ) {

                window.location.href =
                    "/analyze";

            }


            /*
             * V → Validation
             */
            if (
                event.key.toLowerCase() ===
                "v"
            ) {

                window.location.href =
                    "/validation";

            }

        }
    );

}


/* ================================================================
   INITIALIZATION
   ================================================================ */

document.addEventListener(
    "DOMContentLoaded",
    function () {

        console.log(
            "%cLUNARMATCH V2",
            "font-size:18px;font-weight:bold;"
        );

        console.log(
            "Evidence-first lunar image correspondence platform."
        );


        /*
         * Authentication
         */
        wireAuthForms();


        /*
         * Analysis
         */
        wireAnalysisInputs();
        wireAnalyze();


        /*
         * Results
         */
        renderResults();
        wireResultImage();


        /*
         * Validation
         */
        renderValidation();


        /*
         * Stress laboratory
         */
        wireStressLab();


        /*
         * Navigation
         */
        updateActiveNavigation();
        wireMobileNavigation();


        /*
         * Visual polish
         */
        setupRevealEffects();


        /*
         * Backend status
         */
        checkEngineHealth();


        /*
         * Keyboard shortcuts
         */
        wireKeyboardShortcuts();

    }
);
