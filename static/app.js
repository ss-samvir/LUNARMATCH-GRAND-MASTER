```javascript
/* ============================================================
   LUNARMATCH V3
   Frontend application controller
   ============================================================ */

(() => {
    "use strict";

    /* ========================================================
       GLOBAL HELPERS
       ======================================================== */

    const $ = (selector, root = document) =>
        root.querySelector(selector);

    const $$ = (selector, root = document) =>
        Array.from(root.querySelectorAll(selector));

    const escapeHTML = (value) => {
        if (value === null || value === undefined) {
            return "";
        }

        return String(value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    };

    const formatNumber = (value, decimals = 0) => {
        if (value === null || value === undefined || value === "") {
            return "—";
        }

        const number = Number(value);

        if (!Number.isFinite(number)) {
            return "—";
        }

        return number.toFixed(decimals);
    };

    const formatPercent = (value, decimals = 1) => {
        if (value === null || value === undefined) {
            return "—";
        }

        let number = Number(value);

        if (!Number.isFinite(number)) {
            return "—";
        }

        /*
         * In the backend inlier_ratio is stored as a fraction,
         * e.g. 0.42 = 42%.
         */
        if (Math.abs(number) <= 1) {
            number *= 100;
        }

        return `${number.toFixed(decimals)}%`;
    };

    const formatDate = (value) => {
        if (!value) {
            return "—";
        }

        try {
            const date = new Date(value);

            if (Number.isNaN(date.getTime())) {
                return String(value);
            }

            return date.toLocaleString();
        } catch {
            return String(value);
        }
    };


    /* ========================================================
       TOAST
       ======================================================== */

    const showToast = (message, type = "info") => {
        let container = $("#toastContainer");

        if (!container) {
            container = document.createElement("div");
            container.id = "toastContainer";
            container.className = "toast-container";
            document.body.appendChild(container);
        }

        const toast = document.createElement("div");
        toast.className = `toast toast-${type}`;

        toast.innerHTML = `
            <span class="toast-dot"></span>
            <span>${escapeHTML(message)}</span>
        `;

        container.appendChild(toast);

        requestAnimationFrame(() => {
            toast.classList.add("show");
        });

        setTimeout(() => {
            toast.classList.remove("show");

            setTimeout(() => {
                toast.remove();
            }, 300);
        }, 4000);
    };


    /* ========================================================
       API HELPER
       ======================================================== */

    const apiRequest = async (
        url,
        options = {}
    ) => {
        const response = await fetch(
            url,
            {
                credentials: "same-origin",
                ...options,
            }
        );

        let data = null;

        try {
            data = await response.json();
        } catch {
            data = {
                ok: false,
                error: "The server returned an invalid response.",
            };
        }

        if (!response.ok || data.ok === false) {
            const error = new Error(
                data.error || "Something went wrong."
            );

            error.status = response.status;
            error.data = data;

            throw error;
        }

        return data;
    };


    /* ========================================================
       BUTTON LOADING STATE
       ======================================================== */

    const setButtonLoading = (
        button,
        loading,
        text = "Processing..."
    ) => {
        if (!button) {
            return;
        }

        if (loading) {
            if (!button.dataset.originalHTML) {
                button.dataset.originalHTML = button.innerHTML;
            }

            button.disabled = true;

            button.innerHTML = `
                <span class="loading-spinner"></span>
                <span>${escapeHTML(text)}</span>
            `;
        } else {
            button.disabled = false;

            if (button.dataset.originalHTML) {
                button.innerHTML =
                    button.dataset.originalHTML;
            }
        }
    };


    /* ========================================================
       FORM MESSAGE
       ======================================================== */

    const showFormMessage = (
        element,
        message,
        type = "info"
    ) => {
        if (!element) {
            return;
        }

        element.textContent = message;

        element.classList.remove(
            "success",
            "error",
            "info"
        );

        element.classList.add(type);
    };


    /* ========================================================
       MOBILE NAVIGATION
       ======================================================== */

    const initMobileMenu = () => {
        const toggle = $("[data-mobile-menu-toggle]");
        const menu = $("[data-mobile-menu]");

        if (!toggle || !menu) {
            return;
        }

        toggle.addEventListener(
            "click",
            () => {
                const isOpen =
                    menu.classList.toggle("open");

                toggle.setAttribute(
                    "aria-expanded",
                    String(isOpen)
                );
            }
        );

        $$("a", menu).forEach((link) => {
            link.addEventListener(
                "click",
                () => {
                    menu.classList.remove("open");

                    toggle.setAttribute(
                        "aria-expanded",
                        "false"
                    );
                }
            );
        });
    };


    /* ========================================================
       SIGN OUT
       ======================================================== */

    const initSignOut = () => {
        $$("[data-signout]").forEach((button) => {

            button.addEventListener(
                "click",
                async (event) => {

                    event.preventDefault();

                    setButtonLoading(
                        button,
                        true,
                        "Signing out..."
                    );

                    try {

                        const data =
                            await apiRequest(
                                "/api/signout",
                                {
                                    method: "POST",
                                }
                            );

                        window.location.href =
                            data.redirect || "/";

                    } catch (error) {

                        setButtonLoading(
                            button,
                            false
                        );

                        showToast(
                            error.message,
                            "error"
                        );
                    }
                }
            );

        });
    };


    /* ========================================================
       REVEAL ANIMATIONS
       ======================================================== */

    const initRevealAnimations = () => {

        const elements =
            $$(".reveal");

        if (!elements.length) {
            return;
        }

        if (
            !("IntersectionObserver" in window)
        ) {
            elements.forEach(
                (element) =>
                    element.classList.add("visible")
            );

            return;
        }

        const observer =
            new IntersectionObserver(
                (entries) => {

                    entries.forEach(
                        (entry) => {

                            if (
                                entry.isIntersecting
                            ) {
                                entry.target.classList.add(
                                    "visible"
                                );

                                observer.unobserve(
                                    entry.target
                                );
                            }

                        }
                    );

                },
                {
                    threshold: 0.08,
                }
            );

        elements.forEach(
            (element) =>
                observer.observe(element)
        );
    };


    /* ========================================================
       SPACE BACKGROUND
       ======================================================== */

    const initSpaceCanvas = () => {

        const canvas = $("#spaceCanvas");

        if (!canvas) {
            return;
        }

        const context =
            canvas.getContext("2d");

        if (!context) {
            return;
        }

        let width = 0;
        let height = 0;

        const stars = [];

        const STAR_COUNT = 110;

        const resize = () => {

            const ratio =
                Math.min(
                    window.devicePixelRatio || 1,
                    2
                );

            width =
                window.innerWidth;

            height =
                window.innerHeight;

            canvas.width =
                width * ratio;

            canvas.height =
                height * ratio;

            canvas.style.width =
                `${width}px`;

            canvas.style.height =
                `${height}px`;

            context.setTransform(
                ratio,
                0,
                0,
                ratio,
                0,
                0
            );
        };


        const createStars = () => {

            stars.length = 0;

            for (
                let index = 0;
                index < STAR_COUNT;
                index++
            ) {

                stars.push({
                    x:
                        Math.random() *
                        window.innerWidth,

                    y:
                        Math.random() *
                        window.innerHeight,

                    radius:
                        Math.random() *
                        1.4
                        + 0.2,

                    alpha:
                        Math.random() *
                        0.65
                        + 0.15,

                    speed:
                        Math.random() *
                        0.0008
                        + 0.0003,
                });

            }
        };


        const draw = (time) => {

            context.clearRect(
                0,
                0,
                width,
                height
            );

            for (const star of stars) {

                const pulse =
                    Math.sin(
                        time *
                        star.speed
                    ) *
                    0.18;

                const alpha =
                    Math.max(
                        0.05,
                        Math.min(
                            1,
                            star.alpha + pulse
                        )
                    );

                context.beginPath();

                context.arc(
                    star.x,
                    star.y,
                    star.radius,
                    0,
                    Math.PI * 2
                );

                context.globalAlpha =
                    alpha;

                context.fillStyle =
                    "#ffffff";

                context.fill();
            }

            context.globalAlpha = 1;

            window.requestAnimationFrame(
                draw
            );
        };


        resize();
        createStars();

        window.addEventListener(
            "resize",
            () => {
                resize();
                createStars();
            }
        );

        window.requestAnimationFrame(
            draw
        );
    };


    /* ========================================================
       ANALYZE PAGE
       ======================================================== */

    const initAnalyzePage = () => {

        const input = $("#imageInput");

        if (!input) {
            return;
        }

        const selectButton =
            $("#selectImagesBtn");

        const runButton =
            $("#runAnalysisBtn");

        const clearButton =
            $("#clearImagesBtn");

        const acquisitionZone =
            $("#acquisitionZone");

        const imageA =
            $("#imageA");

        const imageB =
            $("#imageB");

        const previewA =
            $("#previewA");

        const previewB =
            $("#previewB");

        const nameA =
            $("#imageAName");

        const nameB =
            $("#imageBName");

        const status =
            $("#acquisitionStatus");

        const loading =
            $("#analysisLoading");

        let selectedFiles = [];


        const updateUI = () => {

            const fileA =
                selectedFiles[0];

            const fileB =
                selectedFiles[1];


            if (fileA) {

                if (previewA) {
                    previewA.src =
                        URL.createObjectURL(fileA);

                    previewA.hidden = false;
                }

                if (imageA) {
                    imageA.classList.add(
                        "has-image"
                    );
                }

                if (nameA) {
                    nameA.textContent =
                        fileA.name;
                }
            }


            if (fileB) {

                if (previewB) {
                    previewB.src =
                        URL.createObjectURL(fileB);

                    previewB.hidden = false;
                }

                if (imageB) {
                    imageB.classList.add(
                        "has-image"
                    );
                }

                if (nameB) {
                    nameB.textContent =
                        fileB.name;
                }
            }


            if (selectedFiles.length === 0) {

                if (status) {
                    status.textContent =
                        "Drop two images or click to select";
                }

            } else if (
                selectedFiles.length === 1
            ) {

                if (status) {
                    status.textContent =
                        "1 image selected — add one more";
                }

            } else {

                if (status) {
                    status.textContent =
                        "Two images ready for correspondence";
                }

            }


            if (runButton) {
                runButton.disabled =
                    selectedFiles.length !== 2;
            }
        };


        const setFiles = (files) => {

            selectedFiles =
                Array.from(files)
                    .filter(
                        (file) =>
                            file.type.startsWith(
                                "image/"
                            )
                    )
                    .slice(0, 2);

            updateUI();
        };


        if (selectButton) {

            selectButton.addEventListener(
                "click",
                () => input.click()
            );

        }


        input.addEventListener(
            "change",
            () => {
                setFiles(input.files);
            }
        );


        if (acquisitionZone) {

            [
                "dragenter",
                "dragover",
            ].forEach(
                (eventName) => {

                    acquisitionZone.addEventListener(
                        eventName,
                        (event) => {

                            event.preventDefault();

                            acquisitionZone.classList.add(
                                "dragging"
                            );
                        }
                    );

                }
            );


            [
                "dragleave",
                "drop",
            ].forEach(
                (eventName) => {

                    acquisitionZone.addEventListener(
                        eventName,
                        (event) => {

                            event.preventDefault();

                            acquisitionZone.classList.remove(
                                "dragging"
                            );
                        }
                    );

                }
            );


            acquisitionZone.addEventListener(
                "drop",
                (event) => {

                    const files =
                        event.dataTransfer.files;

                    setFiles(files);
                }
            );

        }


        if (clearButton) {

            clearButton.addEventListener(
                "click",
                () => {

                    selectedFiles = [];

                    input.value = "";

                    if (previewA) {
                        previewA.src = "";
                        previewA.hidden = true;
                    }

                    if (previewB) {
                        previewB.src = "";
                        previewB.hidden = true;
                    }

                    if (nameA) {
                        nameA.textContent =
                            "Observation A";
                    }

                    if (nameB) {
                        nameB.textContent =
                            "Observation B";
                    }

                    if (imageA) {
                        imageA.classList.remove(
                            "has-image"
                        );
                    }

                    if (imageB) {
                        imageB.classList.remove(
                            "has-image"
                        );
                    }

                    updateUI();
                }
            );

        }


        if (runButton) {

            runButton.addEventListener(
                "click",
                async () => {

                    if (
                        selectedFiles.length !== 2
                    ) {

                        showToast(
                            "Please select exactly two images.",
                            "error"
                        );

                        return;
                    }


                    const formData =
                        new FormData();

                    formData.append(
                        "image_a",
                        selectedFiles[0]
                    );

                    formData.append(
                        "image_b",
                        selectedFiles[1]
                    );


                    if (loading) {
                        loading.hidden = false;
                    }


                    setButtonLoading(
                        runButton,
                        true,
                        "Running correspondence..."
                    );


                    try {

                        const data =
                            await apiRequest(
                                "/api/analyze",
                                {
                                    method: "POST",
                                    body: formData,
                                }
                            );


                        const analysis =
                            data.analysis;

                        if (
                            !analysis ||
                            !analysis.public_id
                        ) {
                            throw new Error(
                                "The server returned an incomplete analysis result."
                            );
                        }


                        /*
                         * Store the complete result temporarily so the
                         * result page can load immediately even if the
                         * query parameter is all that is needed later.
                         */
                        try {
                            sessionStorage.setItem(
                                "lunarmatch_last_analysis",
                                JSON.stringify(
                                    analysis
                                )
                            );
                        } catch {
                            // Storage is optional.
                        }


                        window.location.href =
                            `/results?id=${encodeURIComponent(
                                analysis.public_id
                            )}`;

                    } catch (error) {

                        if (loading) {
                            loading.hidden = true;
                        }

                        setButtonLoading(
                            runButton,
                            false
                        );

                        showToast(
                            error.message,
                            "error"
                        );
                    }

                }
            );

        }


        updateUI();
    };


    /* ========================================================
       RESULTS PAGE
       ======================================================== */

    const initResultsPage = async () => {

        const resultVerdict =
            $("#resultVerdict");

        if (!resultVerdict) {
            return;
        }

        const params =
            new URLSearchParams(
                window.location.search
            );

        const publicId =
            params.get("id");


        let analysis = null;


        /*
         * First try the server.
         * If no ID exists, fall back to sessionStorage.
         */
        try {

            if (publicId) {

                const data =
                    await apiRequest(
                        `/api/results?id=${encodeURIComponent(
                            publicId
                        )}`
                    );

                analysis =
                    data.analysis;
            }

        } catch (error) {

            /*
             * If server loading fails, try the local
             * result from the immediately preceding analysis.
             */
            try {

                const cached =
                    sessionStorage.getItem(
                        "lunarmatch_last_analysis"
                    );

                if (cached) {
                    analysis =
                        JSON.parse(cached);
                }

            } catch {
                analysis = null;
            }

            if (!analysis) {
                showResultError(
                    error.message
                );

                return;
            }
        }


        if (!analysis) {

            try {

                const cached =
                    sessionStorage.getItem(
                        "lunarmatch_last_analysis"
                    );

                if (cached) {
                    analysis =
                        JSON.parse(cached);
                }

            } catch {
                analysis = null;
            }

        }


        if (!analysis) {

            showResultError(
                "No analysis result was supplied."
            );

            return;
        }


        renderResults(
            analysis
        );
    };


    const showResultError = (message) => {

        const summary =
            $("#resultSummary");

        const verdict =
            $("#resultVerdict");

        if (verdict) {
            verdict.textContent =
                "RESULT UNAVAILABLE";
        }

        if (summary) {
            summary.textContent =
                message;
        }

        showToast(
            message,
            "error"
        );
    };


    const setText = (
        selector,
        value
    ) => {

        const element =
            $(selector);

        if (element) {
            element.textContent =
                value ?? "—";
        }
    };


    const renderResults = (
        analysis
    ) => {

        const interpretation =
            analysis.interpretation || {};

        const evidence =
            analysis.evidence || {};

        const components =
            evidence.components || {};

        const geometry =
            analysis.geometry || {};

        const features =
            analysis.features || {};

        const matching =
            analysis.matching || {};

        const quality =
            analysis.quality || {};

        const metadata =
            analysis.metadata || {};

        const metadataA =
            metadata.A || {};

        const metadataB =
            metadata.B || {};

        const validation =
            analysis.validation || {};

        const localization =
            analysis.localization || {};


        /* ---------------------------------------------
           HERO RESULT
           --------------------------------------------- */

        setText(
            "#resultVerdict",
            interpretation.label ||
                "ANALYSIS COMPLETE"
        );

        setText(
            "#resultSummary",
            interpretation.summary ||
                "The analysis has been completed."
        );

        setText(
            "#resultBadge",
            geometry.verified
                ? "GEOMETRICALLY VERIFIED"
                : "NOT GEOMETRICALLY VERIFIED"
        );

        setText(
            "#resultPublicId",
            analysis.public_id || "—"
        );

        setText(
            "#resultScore",
            formatNumber(
                evidence.total,
                2
            )
        );


        /* ---------------------------------------------
           METRICS
           --------------------------------------------- */

        setText(
            "#featuresA",
            formatNumber(
                features.keypoints_A
            )
        );

        setText(
            "#featuresB",
            formatNumber(
                features.keypoints_B
            )
        );

        setText(
            "#candidateMatches",
            formatNumber(
                matching.reciprocal_matches
            )
        );

        setText(
            "#ransacInliers",
            formatNumber(
                geometry.inliers
            )
        );


        /* ---------------------------------------------
           GEOMETRY
           --------------------------------------------- */

        setText(
            "#inlierRatio",
            formatPercent(
                geometry.inlier_ratio,
                2
            )
        );

        setText(
            "#loweRatio",
            formatNumber(
                matching.lowe_ratio,
                2
            )
        );

        setText(
            "#ransacThreshold",
            geometry.ransac_threshold_px !==
            undefined
                ? `${formatNumber(
                    geometry.ransac_threshold_px,
                    1
                )} px`
                : "5.0 px"
        );

        setText(
            "#homographyStatus",
            geometry.verified
                ? "VERIFIED"
                : "NOT VERIFIED"
        );


        /* ---------------------------------------------
           SCORE COMPONENTS
           --------------------------------------------- */

        setText(
            "#scoreCorrespondence",
            formatNumber(
                components.correspondence,
                2
            )
        );

        setText(
            "#scoreGeometry",
            formatNumber(
                components.geometric_consistency,
                2
            )
        );

        setText(
            "#scoreInliers",
            formatNumber(
                components.inlier_count,
                2
            )
        );

        setText(
            "#scoreQuality",
            formatNumber(
                components.image_quality,
                2
            )
        );


        /* ---------------------------------------------
           VISUALIZATION
           --------------------------------------------- */

        const visualization =
            $("#resultVisualization");

        if (
            visualization &&
            analysis.visualization_url
        ) {

            visualization.src =
                analysis.visualization_url;

            visualization.hidden =
                false;

        } else if (visualization) {

            visualization.hidden =
                true;
        }


        /* ---------------------------------------------
           IMAGE QUALITY
           --------------------------------------------- */

        renderQuality(
            "#qualityA",
            quality.A
        );

        renderQuality(
            "#qualityB",
            quality.B
        );


        /* ---------------------------------------------
           METADATA
           --------------------------------------------- */

        renderMetadata(
            "A",
            metadataA
        );

        renderMetadata(
            "B",
            metadataB
        );


        /* ---------------------------------------------
           LOCALIZATION
           --------------------------------------------- */

        setText(
            "#coordinateStatus",
            localization.status ===
            "AVAILABLE"
                ? "AVAILABLE"
                : "NOT AVAILABLE"
        );

        setText(
            "#coordinateLatitude",
            localization.latitude !==
            null &&
            localization.latitude !==
            undefined
                ? formatNumber(
                    localization.latitude,
                    8
                )
                : "—"
        );

        setText(
            "#coordinateLongitude",
            localization.longitude !==
            null &&
            localization.longitude !==
            undefined
                ? formatNumber(
                    localization.longitude,
                    8
                )
                : "—"
        );

        setText(
            "#coordinateBasis",
            localization.basis ||
                "No trusted coordinate source was available."
        );


        /* ---------------------------------------------
           VALIDATION
           --------------------------------------------- */

        renderValidation(
            validation
        );


        /* ---------------------------------------------
           WARNINGS
           --------------------------------------------- */

        renderWarnings(
            validation.warnings || [],
            "#resultWarnings"
        );


        /* ---------------------------------------------
           REPORT
           --------------------------------------------- */

        const reportButton =
            $("#downloadReportBtn");

        if (reportButton) {

            if (analysis.public_id) {

                reportButton.dataset.publicId =
                    analysis.public_id;

                reportButton.addEventListener(
                    "click",
                    () => {

                        window.location.href =
                            `/api/report/${encodeURIComponent(
                                analysis.public_id
                            )}`;
                    }
                );

            } else {

                reportButton.disabled = true;
            }
        }


        /*
         * Make the current result available to the
         * validation page.
         */
        try {

            sessionStorage.setItem(
                "lunarmatch_last_analysis",
                JSON.stringify(
                    analysis
                )
            );

        } catch {
            // Optional storage.
        }
    };


    const renderQuality = (
        prefix,
        quality
    ) => {

        if (!quality) {
            return;
        }

        setText(
            `${prefix}Score`,
            formatNumber(
                quality.quality_score,
                2
            )
        );

        setText(
            `${prefix}Contrast`,
            formatNumber(
                quality.contrast,
                2
            )
        );

        setText(
            `${prefix}Sharpness`,
            formatNumber(
                quality.sharpness,
                2
            )
        );

        setText(
            `${prefix}Brightness`,
            formatNumber(
                quality.brightness,
                2
            )
        );
    };


    const renderMetadata = (
        letter,
        metadata
    ) => {

        if (!metadata) {
            return;
        }

        const prefix =
            `#metadata${letter}`;

        const mapping = {
            latitude:
                metadata.latitude !== null &&
                metadata.latitude !== undefined
                    ? formatNumber(
                        metadata.latitude,
                        8
                    )
                    : "—",

            longitude:
                metadata.longitude !== null &&
                metadata.longitude !== undefined
                    ? formatNumber(
                        metadata.longitude,
                        8
                    )
                    : "—",

            altitude:
                metadata.altitude !== null &&
                metadata.altitude !== undefined
                    ? formatNumber(
                        metadata.altitude,
                        3
                    )
                    : "—",

            acquisitionTime:
                metadata.acquisition_time ||
                "—",

            instrument:
                metadata.instrument ||
                "—",

            mission:
                metadata.mission ||
                "—",

            projection:
                metadata.projection ||
                "—",
        };


        Object.entries(mapping).forEach(
            ([key, value]) => {

                const element =
                    $(`${prefix}${key}`);

                if (element) {
                    element.textContent =
                        value;
                }
            }
        );
    };


    const renderValidation = (
        validation
    ) => {

        const instruments =
            validation.instrument || {};

        const instrumentA =
            instruments.A || {};

        const instrumentB =
            instruments.B || {};

        setText(
            "#validationInstrumentA",
            instrumentA.status ===
            "ESTABLISHED"
                ? instrumentA.code
                : "NOT ESTABLISHED"
        );

        setText(
            "#validationInstrumentB",
            instrumentB.status ===
            "ESTABLISHED"
                ? instrumentB.code
                : "NOT ESTABLISHED"
        );


        const mission =
            validation.mission_validation ||
            {};

        setText(
            "#validationMissionStatus",
            mission.status ||
                "METADATA_ONLY"
        );


        const projection =
            validation.projection_validation ||
            {};

        setText(
            "#validationProjectionStatus",
            projection.status ||
                "NOT AVAILABLE"
        );


        const reference =
            validation.reference_validation ||
            {};

        setText(
            "#validationReferenceStatus",
            reference.status ||
                "NOT AVAILABLE"
        );
    };


    const renderWarnings = (
        warnings,
        selector
    ) => {

        const container =
            $(selector);

        if (!container) {
            return;
        }

        container.innerHTML = "";

        if (!warnings.length) {

            container.innerHTML =
                `<div class="warning-item success">
                    No validation warnings were reported.
                </div>`;

            return;
        }


        warnings.forEach(
            (warning) => {

                const item =
                    document.createElement(
                        "div"
                    );

                item.className =
                    "warning-item";

                item.textContent =
                    warning;

                container.appendChild(
                    item
                );
            }
        );
    };


    /* ========================================================
       VALIDATION PAGE
       ======================================================== */

    const initValidationPage = async () => {

        const validationMarker =
            $("#currentValidation");

        if (!validationMarker) {
            return;
        }

        const params =
            new URLSearchParams(
                window.location.search
            );

        const publicId =
            params.get("id");


        let analysis = null;


        try {

            if (publicId) {

                const data =
                    await apiRequest(
                        `/api/results?id=${encodeURIComponent(
                            publicId
                        )}`
                    );

                analysis =
                    data.analysis;

            } else {

                const cached =
                    sessionStorage.getItem(
                        "lunarmatch_last_analysis"
                    );

                if (cached) {
                    analysis =
                        JSON.parse(cached);
                }
            }

        } catch (error) {

            showToast(
                error.message,
                "error"
            );

            return;
        }


        if (!analysis) {

            setText(
                "#currentValidationStatus",
                "NO ANALYSIS LOADED"
            );

            setText(
                "#currentValidationMessage",
                "Run an analysis first, then open validation."
            );

            return;
        }


        const validation =
            analysis.validation || {};

        const localization =
            analysis.localization || {};


        setText(
            "#currentValidationStatus",
            validation.overall ||
                "PARTIAL"
        );

        setText(
            "#currentValidationMessage",
            validation.mission_validation?.text ||
                "Validation evidence is derived from available metadata."
        );


        setText(
            "#validationCoordinateStatus",
            localization.status ||
                "NOT_AVAILABLE"
        );

        setText(
            "#validationLatitude",
            localization.latitude !== null &&
            localization.latitude !== undefined
                ? formatNumber(
                    localization.latitude,
                    8
                )
                : "—"
        );

        setText(
            "#validationLongitude",
            localization.longitude !== null &&
            localization.longitude !== undefined
                ? formatNumber(
                    localization.longitude,
                    8
                )
                : "—"
        );


        const instruments =
            validation.instrument || {};

        setText(
            "#validationAInstrument",
            instruments.A?.status ===
            "ESTABLISHED"
                ? instruments.A.code
                : "NOT ESTABLISHED"
        );

        setText(
            "#validationBInstrument",
            instruments.B?.status ===
            "ESTABLISHED"
                ? instruments.B.code
                : "NOT ESTABLISHED"
        );


        setText(
            "#validationAMission",
            analysis.metadata?.A?.mission ||
                "—"
        );

        setText(
            "#validationBMission",
            analysis.metadata?.B?.mission ||
                "—"
        );


        const projection =
            validation.projection_validation ||
            {};

        setText(
            "#validationProjection",
            projection.projection ||
                "NOT AVAILABLE"
        );

        setText(
            "#validationCRS",
            projection.crs ||
                "NOT AVAILABLE"
        );


        renderWarnings(
            validation.warnings || [],
            "#validationWarnings"
        );
    };


    /* ========================================================
       STRESS LAB
       ======================================================== */

    const initStressPage = () => {

        const imageInput =
            $("#stressImage");

        if (!imageInput) {
            return;
        }

        const runButton =
            $("#runStressBtn");

        const typeInput =
            $("#stressMode");

        const severityInput =
            $("#stressStrength");


        const updateSeverityLabel = () => {

            const label =
                $("#stressStrengthValue");

            if (
                label &&
                severityInput
            ) {
                label.textContent =
                    `${Math.round(
                        Number(
                            severityInput.value
                        ) * 100
                    )}%`;
            }
        };


        if (severityInput) {

            severityInput.addEventListener(
                "input",
                updateSeverityLabel
            );

            updateSeverityLabel();
        }


        if (!runButton) {
            return;
        }


        runButton.addEventListener(
            "click",
            async () => {

                const file =
                    imageInput.files?.[0];

                if (!file) {

                    showToast(
                        "Please select a reference image.",
                        "error"
                    );

                    return;
                }


                const formData =
                    new FormData();

                formData.append(
                    "image",
                    file
                );

                formData.append(
                    "type",
                    typeInput?.value ||
                        "noise"
                );

                formData.append(
                    "severity",
                    severityInput?.value ||
                        "0.5"
                );


                setButtonLoading(
                    runButton,
                    true,
                    "Running stress test..."
                );


                try {

                    const data =
                        await apiRequest(
                            "/api/stress",
                            {
                                method: "POST",
                                body: formData,
                            }
                        );


                    renderStressResult(
                        data.stress
                    );

                    showToast(
                        "Stress test completed.",
                        "success"
                    );

                } catch (error) {

                    showToast(
                        error.message,
                        "error"
                    );

                } finally {

                    setButtonLoading(
                        runButton,
                        false
                    );
                }

            }
        );
    };


    const renderStressResult = (
        stress
    ) => {

        if (!stress) {
            return;
        }

        const baseline =
            stress.baseline || {};

        const test =
            stress.test || {};


        setText(
            "#stressBaselineScore",
            formatNumber(
                baseline.score,
                2
            )
        );

        setText(
            "#stressTestScore",
            formatNumber(
                test.score,
                2
            )
        );

        setText(
            "#stressScoreChange",
            formatNumber(
                stress.score_change,
                2
            )
        );

        setText(
            "#stressStability",
            `${formatNumber(
                stress.stability,
                2
            )}%`
        );

        setText(
            "#stressMatches",
            formatNumber(
                test.matches
            )
        );

        setText(
            "#stressInliers",
            formatNumber(
                test.inliers
            )
        );

        setText(
            "#stressInlierRatio",
            formatPercent(
                test.inlier_ratio,
                2
            )
        );

        setText(
            "#stressVerification",
            test.verified
                ? "VERIFIED"
                : "NOT VERIFIED"
        );

        setText(
            "#stressInterpretation",
            stress.interpretation ||
                "—"
        );


        const transformedImage =
            $("#stressTransformedImage");

        if (
            transformedImage &&
            stress.transformed_image
        ) {

            transformedImage.src =
                stress.transformed_image;

            transformedImage.hidden =
                false;
        }


        /*
         * Fill the stress table if the page contains
         * a table body.
         */
        const tableBody =
            $("#stressTableBody");

        if (tableBody) {

            tableBody.innerHTML = `
                <tr>
                    <td>Baseline</td>
                    <td>${formatNumber(
                        baseline.score,
                        2
                    )}</td>
                    <td>${formatNumber(
                        baseline.matches
                    )}</td>
                    <td>${formatNumber(
                        baseline.inliers
                    )}</td>
                    <td>${formatPercent(
                        baseline.inlier_ratio,
                        2
                    )}</td>
                    <td>
                        ${baseline.verified
                            ? "VERIFIED"
                            : "NOT VERIFIED"}
                    </td>
                </tr>

                <tr>
                    <td>${escapeHTML(
                        stress.type
                    )}</td>
                    <td>${formatNumber(
                        test.score,
                        2
                    )}</td>
                    <td>${formatNumber(
                        test.matches
                    )}</td>
                    <td>${formatNumber(
                        test.inliers
                    )}</td>
                    <td>${formatPercent(
                        test.inlier_ratio,
                        2
                    )}</td>
                    <td>
                        ${test.verified
                            ? "VERIFIED"
                            : "NOT VERIFIED"}
                    </td>
                </tr>
            `;
        }
    };


    /* ========================================================
       SIGN UP
       ======================================================== */

    const initSignup = () => {

        const form =
            $("#signupForm");

        if (!form) {
            return;
        }

        const button =
            $("#signupBtn");

        const message =
            $("#signupMessage");

        const profession =
            $("#signupProfession");

        const studentFields =
            $("#studentFields");

        const course =
            $("#signupCourse");

        const studyYear =
            $("#signupStudyYear");

        const password =
            $("#signupPassword");

        const confirmPassword =
            $("#signupPasswordConfirm");


        const updateStudentFields = () => {

            const isStudent =
                profession?.value ===
                "student";

            if (studentFields) {

                studentFields.classList.toggle(
                    "active",
                    isStudent
                );
            }

            if (course) {
                course.required =
                    isStudent;
            }

            if (studyYear) {
                studyYear.required =
                    isStudent;
            }
        };


        if (profession) {

            profession.addEventListener(
                "change",
                updateStudentFields
            );

            updateStudentFields();
        }


        form.addEventListener(
            "submit",
            async (event) => {

                event.preventDefault();


                if (
                    password?.value !==
                    confirmPassword?.value
                ) {

                    showFormMessage(
                        message,
                        "Passwords do not match.",
                        "error"
                    );

                    return;
                }


                if (
                    password?.value.length < 8
                ) {

                    showFormMessage(
                        message,
                        "Password must contain at least 8 characters.",
                        "error"
                    );

                    return;
                }


                const formData =
                    new FormData(form);

                const payload =
                    Object.fromEntries(
                        formData.entries()
                    );

                delete payload.password_confirm;


                setButtonLoading(
                    button,
                    true,
                    "Creating account..."
                );


                try {

                    const data =
                        await apiRequest(
                            "/api/signup",
                            {
                                method: "POST",

                                headers: {
                                    "Content-Type":
                                        "application/json",
                                },

                                body:
                                    JSON.stringify(
                                        payload
                                    ),
                            }
                        );


                    showFormMessage(
                        message,
                        data.message ||
                            "Account created successfully.",
                        "success"
                    );


                    if (
                        data.welcome_email?.sent
                    ) {

                        showToast(
                            "Welcome email sent successfully.",
                            "success"
                        );

                    } else {

                        showToast(
                            "Account created. Email service is not currently configured.",
                            "info"
                        );
                    }


                    setTimeout(
                        () => {

                            window.location.href =
                                data.redirect ||
                                "/workspace";

                        },
                        900
                    );

                } catch (error) {

                    showFormMessage(
                        message,
                        error.message,
                        "error"
                    );

                    setButtonLoading(
                        button,
                        false
                    );
                }

            }
        );
    };


    /* ========================================================
       SIGN IN
       ======================================================== */

    const initSignin = () => {

        const form =
            $("#signinForm");

        if (!form) {
            return;
        }

        const button =
            $("#signinBtn");

        const message =
            $("#signinMessage");


        form.addEventListener(
            "submit",
            async (event) => {

                event.preventDefault();


                const identity =
                    $("#signinIdentifier")
                        ?.value
                        .trim();

                const password =
                    $("#signinPassword")
                        ?.value;


                if (
                    !identity ||
                    !password
                ) {

                    showFormMessage(
                        message,
                        "Please enter your username/email and password.",
                        "error"
                    );

                    return;
                }


                setButtonLoading(
                    button,
                    true,
                    "Signing in..."
                );


                try {

                    const data =
                        await apiRequest(
                            "/api/signin",
                            {
                                method: "POST",

                                headers: {
                                    "Content-Type":
                                        "application/json",
                                },

                                body:
                                    JSON.stringify({
                                        identity,
                                        password,
                                    }),
                            }
                        );


                    showFormMessage(
                        message,
                        data.message ||
                            "Signed in successfully.",
                        "success"
                    );


                    setTimeout(
                        () => {

                            window.location.href =
                                data.redirect ||
                                "/workspace";

                        },
                        500
                    );

                } catch (error) {

                    showFormMessage(
                        message,
                        error.message,
                        "error"
                    );

                    setButtonLoading(
                        button,
                        false
                    );
                }

            }
        );
    };


    /* ========================================================
       FEEDBACK
       ======================================================== */

    const initFeedback = () => {

        const form =
            $("#feedbackForm");

        if (!form) {
            return;
        }

        const button =
            $("#submitFeedbackBtn");

        const message =
            $("#feedbackMessageBox");


        form.addEventListener(
            "submit",
            async (event) => {

                event.preventDefault();


                const formData =
                    new FormData(form);

                const payload =
                    Object.fromEntries(
                        formData.entries()
                    );


                if (!payload.rating) {
                    payload.rating = null;
                }


                setButtonLoading(
                    button,
                    true,
                    "Submitting..."
                );


                try {

                    const data =
                        await apiRequest(
                            "/api/feedback",
                            {
                                method: "POST",

                                headers: {
                                    "Content-Type":
                                        "application/json",
                                },

                                body:
                                    JSON.stringify(
                                        payload
                                    ),
                            }
                        );


                    showFormMessage(
                        message,
                        data.message ||
                            "Thank you for your feedback.",
                        "success"
                    );

                    showToast(
                        "Feedback recorded successfully.",
                        "success"
                    );


                    form.reset();

                } catch (error) {

                    showFormMessage(
                        message,
                        error.message,
                        "error"
                    );

                } finally {

                    setButtonLoading(
                        button,
                        false
                    );
                }

            }
        );
    };


    /* ========================================================
       WORKSPACE
       ======================================================== */

    const initWorkspace = async () => {

        const historyBody =
            $("#workspaceHistoryBody");

        if (!historyBody) {
            return;
        }

        const loading =
            $("#workspaceHistoryLoading");

        const empty =
            $("#workspaceHistoryEmpty");

        const errorBox =
            $("#workspaceHistoryError");

        const errorText =
            $("#workspaceHistoryErrorText");

        const table =
            $("#workspaceHistoryTable");

        const refresh =
            $("#refreshHistoryBtn");

        const retry =
            $("#retryHistoryBtn");


        const loadProfile = async () => {

            try {

                const data =
                    await apiRequest(
                        "/api/profile"
                    );

                const profile =
                    data.profile || {};


                setText(
                    "#workspaceName",
                    profile.name ||
                        "LUNARMATCH User"
                );

                setText(
                    "#workspaceRole",
                    profile.profession ||
                        "LUNARMATCH User"
                );

                setText(
                    "#workspaceUsername",
                    profile.username ||
                        "—"
                );

                setText(
                    "#workspaceEmail",
                    profile.email ||
                        "—"
                );

                setText(
                    "#workspaceInstitution",
                    profile.institution ||
                        "—"
                );

                setText(
                    "#workspaceResearchArea",
                    profile.research_area ||
                        "—"
                );


                const avatar =
                    $("#workspaceAvatar");

                if (avatar) {

                    avatar.textContent =
                        (
                            profile.name ||
                            "L"
                        )
                            .trim()
                            .charAt(0)
                            .toUpperCase();
                }

            } catch (error) {

                showToast(
                    error.message,
                    "error"
                );
            }
        };


        const loadHistory = async () => {

            if (loading) {
                loading.hidden = false;
            }

            if (empty) {
                empty.hidden = true;
            }

            if (errorBox) {
                errorBox.hidden = true;
            }

            if (table) {
                table.hidden = true;
            }


            try {

                const data =
                    await apiRequest(
                        "/api/results"
                    );

                const analyses =
                    data.analyses || [];


                setText(
                    "#workspaceAnalysisCount",
                    analyses.length
                );

                setText(
                    "#workspaceVerifiedCount",
                    analyses.filter(
                        (item) =>
                            Boolean(
                                item.verified
                            )
                    ).length
                );


                historyBody.innerHTML = "";


                if (!analyses.length) {

                    if (loading) {
                        loading.hidden = true;
                    }

                    if (empty) {
                        empty.hidden = false;
                    }

                    return;
                }


                analyses.forEach(
                    (item) => {

                        const row =
                            document.createElement(
                                "tr"
                            );

                        const verified =
                            Boolean(
                                item.verified
                            );


                        row.innerHTML = `
                            <td>
                                ${escapeHTML(
                                    formatDate(
                                        item.created_at
                                    )
                                )}
                            </td>

                            <td>
                                <code>
                                    ${escapeHTML(
                                        item.public_id
                                    )}
                                </code>
                            </td>

                            <td>
                                ${formatNumber(
                                    item.score,
                                    2
                                )}
                            </td>

                            <td>
                                <span class="badge ${
                                    verified
                                        ? "badge-success"
                                        : "badge-info"
                                }">
                                    ${
                                        verified
                                            ? "VERIFIED"
                                            : "ANALYZED"
                                    }
                                </span>
                            </td>

                            <td>
                                <a
                                    href="/results?id=${encodeURIComponent(
                                        item.public_id
                                    )}"
                                    class="btn btn-small btn-secondary"
                                >
                                    Open
                                </a>
                            </td>
                        `;


                        historyBody.appendChild(
                            row
                        );
                    }
                );


                if (loading) {
                    loading.hidden = true;
                }

                if (table) {
                    table.hidden = false;
                }

            } catch (error) {

                if (loading) {
                    loading.hidden = true;
                }

                if (errorBox) {
                    errorBox.hidden = false;
                }

                if (errorText) {
                    errorText.textContent =
                        error.message;
                }
            }
        };


        if (refresh) {

            refresh.addEventListener(
                "click",
                async () => {

                    setButtonLoading(
                        refresh,
                        true,
                        "Refreshing..."
                    );

                    await loadHistory();

                    setButtonLoading(
                        refresh,
                        false
                    );
                }
            );
        }


        if (retry) {

            retry.addEventListener(
                "click",
                loadHistory
            );
        }


        await loadProfile();
        await loadHistory();
    };


    /* ========================================================
       CONTACT / SIMPLE MAIL LINKS
       ======================================================== */

    const initContactLinks = () => {

        $$('a[href^="mailto:"]').forEach(
            (link) => {

                link.addEventListener(
                    "click",
                    () => {

                        /*
                         * Intentionally no fake contact API.
                         * mailto opens the user's configured email client.
                         */
                    }
                );

            }
        );
    };


    /* ========================================================
       INITIALIZE
       ======================================================== */

    const init = () => {

        initSpaceCanvas();

        initMobileMenu();

        initSignOut();

        initRevealAnimations();

        initAnalyzePage();

        initResultsPage();

        initValidationPage();

        initStressPage();

        initSignup();

        initSignin();

        initFeedback();

        initWorkspace();

        initContactLinks();
    };


    if (
        document.readyState ===
        "loading"
    ) {

        document.addEventListener(
            "DOMContentLoaded",
            init
        );

    } else {

        init();
    }

})();
```
