```javascript
/* =========================================================
   LUNARMATCH V3 — MAIN APPLICATION JAVASCRIPT
   Research-grade lunar image correspondence interface
   Backend: Flask /api/*
   ========================================================= */

(() => {
    "use strict";

    /* ---------------------------------------------------------
       GLOBAL STATE
    --------------------------------------------------------- */

    const state = {
        user: null,
        latestResult: null,
        analysisRunning: false,
        selectedFiles: {
            a: null,
            b: null
        }
    };

    const $ = (selector, root = document) => root.querySelector(selector);
    const $$ = (selector, root = document) =>
        Array.from(root.querySelectorAll(selector));

    /* ---------------------------------------------------------
       INITIALIZATION
    --------------------------------------------------------- */

    document.addEventListener("DOMContentLoaded", async () => {
        initNavigation();
        initMobileNavigation();
        initRevealAnimations();
        initTiltCards();
        initSpaceCanvas();
        initFileInputs();
        initForms();
        initAnalysis();
        initFeedback();
        initStressTesting();
        initResultActions();

        await loadCurrentUser();
        loadStoredResult();
        updateAuthenticatedUI();
    });

    /* ---------------------------------------------------------
       API HELPER
    --------------------------------------------------------- */

    async function api(url, options = {}) {
        const config = {
            credentials: "same-origin",
            ...options
        };

        if (
            config.body &&
            typeof config.body === "object" &&
            !(config.body instanceof FormData) &&
            !(config.body instanceof Blob)
        ) {
            config.headers = {
                "Content-Type": "application/json",
                ...(config.headers || {})
            };
            config.body = JSON.stringify(config.body);
        }

        let response;

        try {
            response = await fetch(url, config);
        } catch (error) {
            throw new Error(
                "Unable to connect to LUNARMATCH. Please check your connection and try again."
            );
        }

        let data = null;

        const contentType = response.headers.get("content-type") || "";

        if (contentType.includes("application/json")) {
            try {
                data = await response.json();
            } catch (_) {
                data = null;
            }
        } else {
            try {
                data = await response.text();
            } catch (_) {
                data = null;
            }
        }

        if (!response.ok) {
            const message =
                data && typeof data === "object" && data.error
                    ? data.error
                    : `Request failed (${response.status})`;

            throw new Error(message);
        }

        return data;
    }

    /* ---------------------------------------------------------
       AUTHENTICATION
    --------------------------------------------------------- */

    async function loadCurrentUser() {
        try {
            const data = await api("/api/profile");

            if (data && data.authenticated) {
                state.user = data.user || null;
            } else {
                state.user = null;
            }
        } catch (_) {
            state.user = null;
        }
    }

    function updateAuthenticatedUI() {
        const authElements = $$("[data-auth-only]");
        const guestElements = $$("[data-guest-only]");
        const userNames = $$("[data-user-name]");
        const userEmails = $$("[data-user-email]");

        authElements.forEach(el => {
            el.hidden = !state.user;
        });

        guestElements.forEach(el => {
            el.hidden = !!state.user;
        });

        if (state.user) {
            userNames.forEach(el => {
                el.textContent =
                    state.user.name ||
                    state.user.username ||
                    "Researcher";
            });

            userEmails.forEach(el => {
                el.textContent = state.user.email || "";
            });
        }
    }

    async function handleSignIn(form) {
        const submitButton = getSubmitButton(form);
        setButtonLoading(submitButton, true, "SIGNING IN...");

        try {
            const identity =
                getFieldValue(form, [
                    "identity",
                    "username",
                    "email"
                ]) || "";

            const password = getFieldValue(form, ["password"]) || "";

            if (!identity || !password) {
                throw new Error("Enter your username/email and password.");
            }

            const data = await api("/api/signin", {
                method: "POST",
                body: {
                    identity,
                    password
                }
            });

            state.user = data.user || null;

            showToast(
                "Welcome back to LUNARMATCH.",
                "success"
            );

            updateAuthenticatedUI();

            const redirect =
                form.dataset.redirect ||
                "/workspace";

            setTimeout(() => {
                window.location.href = redirect;
            }, 500);

        } catch (error) {
            showFormMessage(form, error.message, "error");
        } finally {
            setButtonLoading(submitButton, false);
        }
    }

    async function handleSignUp(form) {
        const submitButton = getSubmitButton(form);
        setButtonLoading(submitButton, true, "CREATING ACCOUNT...");

        try {
            const data = collectFormData(form);

            if (!data.name) {
                throw new Error("Please enter your name.");
            }

            if (!data.email) {
                throw new Error("Please enter your email address.");
            }

            if (!data.username) {
                throw new Error("Please choose a username.");
            }

            if (!data.password || data.password.length < 8) {
                throw new Error(
                    "Password must contain at least 8 characters."
                );
            }

            if (!data.profession) {
                throw new Error("Please select your profession/role.");
            }

            if (!data.institution) {
                throw new Error(
                    "Please enter your college, institution or organization."
                );
            }

            const result = await api("/api/signup", {
                method: "POST",
                body: data
            });

            if (result.email && result.email.sent) {
                showToast(
                    "Account created. Your LUNARMATCH welcome email was sent.",
                    "success"
                );
            } else {
                showToast(
                    "Account created successfully.",
                    "success"
                );
            }

            showFormMessage(
                form,
                result.message ||
                    "Your LUNARMATCH research account is ready.",
                "success"
            );

            setTimeout(() => {
                window.location.href =
                    form.dataset.redirect || "/signin";
            }, 900);

        } catch (error) {
            showFormMessage(form, error.message, "error");
        } finally {
            setButtonLoading(submitButton, false);
        }
    }

    async function handleSignOut() {
        try {
            await api("/api/signout", {
                method: "POST"
            });
        } catch (_) {
            // Even if the network request fails, refresh the UI.
        }

        state.user = null;
        updateAuthenticatedUI();

        showToast("Signed out successfully.", "success");

        setTimeout(() => {
            window.location.href = "/";
        }, 500);
    }

    /* ---------------------------------------------------------
       FORM INITIALIZATION
    --------------------------------------------------------- */

    function initForms() {
        $$("form[data-form='signin']").forEach(form => {
            form.addEventListener("submit", event => {
                event.preventDefault();
                handleSignIn(form);
            });
        });

        $$("form[data-form='signup']").forEach(form => {
            form.addEventListener("submit", event => {
                event.preventDefault();
                handleSignUp(form);
            });
        });

        $$("form[data-form='feedback']").forEach(form => {
            form.addEventListener("submit", event => {
                event.preventDefault();
                handleFeedback(form);
            });
        });

        $$("[data-signout]").forEach(button => {
            button.addEventListener("click", event => {
                event.preventDefault();
                handleSignOut();
            });
        });

        initPasswordToggles();
        initConditionalFields();
    }

    function collectFormData(form) {
        const data = {};
        const formData = new FormData(form);

        formData.forEach((value, key) => {
            data[key] = typeof value === "string"
                ? value.trim()
                : value;
        });

        return data;
    }

    function getFieldValue(form, names) {
        for (const name of names) {
            const field = form.elements[name];

            if (field && field.value !== undefined) {
                return field.value.trim();
            }
        }

        return "";
    }

    function getSubmitButton(form) {
        return (
            $("button[type='submit']", form) ||
            $("input[type='submit']", form)
        );
    }

    function setButtonLoading(button, loading, text) {
        if (!button) return;

        if (loading) {
            button.dataset.originalText =
                button.textContent || button.value || "";

            button.disabled = true;

            if ("value" in button && button.tagName === "INPUT") {
                button.value = text;
            } else {
                button.textContent = text;
            }

            button.classList.add("is-loading");
        } else {
            button.disabled = false;

            const original =
                button.dataset.originalText || "";

            if ("value" in button && button.tagName === "INPUT") {
                button.value = original;
            } else if (original) {
                button.textContent = original;
            }

            button.classList.remove("is-loading");
        }
    }

    function showFormMessage(form, message, type = "info") {
        let box = $(".form-message", form);

        if (!box) {
            box = document.createElement("div");
            box.className = "form-message";
            form.prepend(box);
        }

        box.textContent = message;
        box.dataset.type = type;
        box.hidden = false;
    }

    /* ---------------------------------------------------------
       CONDITIONAL SIGNUP FIELDS
    --------------------------------------------------------- */

    function initConditionalFields() {
        const professionFields = $$(
            "select[name='profession'], [data-profession-select]"
        );

        professionFields.forEach(select => {
            const update = () => {
                const value = select.value.toLowerCase();

                const studentFields = $$(
                    "[data-student-fields]"
                );

                const researchFields = $$(
                    "[data-research-fields]"
                );

                const isStudent =
                    value.includes("student") ||
                    value.includes("undergraduate") ||
                    value.includes("postgraduate");

                const isResearcher =
                    value.includes("research") ||
                    value.includes("scientist") ||
                    value.includes("professional");

                studentFields.forEach(el => {
                    el.hidden = !isStudent;
                });

                researchFields.forEach(el => {
                    el.hidden = !isResearcher;
                });
            };

            select.addEventListener("change", update);
            update();
        });
    }

    function initPasswordToggles() {
        $$("[data-password-toggle]").forEach(button => {
            button.addEventListener("click", () => {
                const targetSelector =
                    button.dataset.passwordToggle;

                const input =
                    $(targetSelector) ||
                    button.closest(".password-field")?.querySelector("input");

                if (!input) return;

                input.type =
                    input.type === "password"
                        ? "text"
                        : "password";

                button.setAttribute(
                    "aria-label",
                    input.type === "password"
                        ? "Show password"
                        : "Hide password"
                );
            });
        });
    }

    /* ---------------------------------------------------------
       IMAGE ACQUISITION
       --------------------------------------------------------- */

    function initFileInputs() {
        const zones = $$("[data-dropzone]");

        zones.forEach(zone => {
            const target =
                zone.dataset.dropzone ||
                zone.dataset.target ||
                "";

            const input =
                target
                    ? $(target)
                    : zone.querySelector("input[type='file']");

            if (!input) return;

            zone.addEventListener("click", event => {
                if (event.target.closest("button, a, input")) return;
                input.click();
            });

            ["dragenter", "dragover"].forEach(type => {
                zone.addEventListener(type, event => {
                    event.preventDefault();
                    zone.classList.add("drag-active");
                });
            });

            ["dragleave", "drop"].forEach(type => {
                zone.addEventListener(type, event => {
                    event.preventDefault();
                    zone.classList.remove("drag-active");
                });
            });

            zone.addEventListener("drop", event => {
                const files = event.dataTransfer.files;

                if (!files || !files.length) return;

                if (input.multiple) {
                    input.files = files;
                    input.dispatchEvent(new Event("change", {
                        bubbles: true
                    }));
                } else {
                    const file = files[0];

                    try {
                        const transfer = new DataTransfer();
                        transfer.items.add(file);
                        input.files = transfer.files;
                        input.dispatchEvent(new Event("change", {
                            bubbles: true
                        }));
                    } catch (_) {
                        showToast(
                            "Please select the image using the file picker.",
                            "error"
                        );
                    }
                }
            });

            input.addEventListener("change", () => {
                handleImageSelection(input, zone);
            });
        });

        /*
         * Unified acquisition mode:
         * An input can accept exactly two images with
         * data-image-pair="true".
         */
        $$("input[data-image-pair='true']").forEach(input => {
            input.addEventListener("change", () => {
                const files = Array.from(input.files || []);

                if (files.length > 2) {
                    showToast(
                        "Please select exactly two images.",
                        "error"
                    );

                    input.value = "";
                    return;
                }

                files.forEach((file, index) => {
                    if (index === 0) {
                        state.selectedFiles.a = file;
                    }

                    if (index === 1) {
                        state.selectedFiles.b = file;
                    }
                });

                updateUnifiedAcquisitionPreview();
            });
        });
    }

    function handleImageSelection(input, zone) {
        const file = input.files?.[0];

        if (!file) return;

        if (!file.type.startsWith("image/")) {
            showToast(
                "Please select a valid image file.",
                "error"
            );

            input.value = "";
            return;
        }

        const maxBytes = 25 * 1024 * 1024;

        if (file.size > maxBytes) {
            showToast(
                "This image exceeds the 25 MB upload limit.",
                "error"
            );

            input.value = "";
            return;
        }

        const target =
            input.dataset.target ||
            zone.dataset.preview ||
            "";

        if (target) {
            const preview = $(target);

            if (preview) {
                renderImagePreview(file, preview);
            }
        }

        const filename =
            zone.querySelector("[data-file-name]");

        if (filename) {
            filename.textContent = file.name;
        }

        zone.classList.add("has-file");

        const slot = input.dataset.slot;

        if (slot === "a") {
            state.selectedFiles.a = file;
        }

        if (slot === "b") {
            state.selectedFiles.b = file;
        }

        updateUnifiedAcquisitionPreview();
    }

    function renderImagePreview(file, element) {
        if (!element) return;

        const url = URL.createObjectURL(file);

        if (element.tagName === "IMG") {
            element.src = url;
            element.alt = file.name;
        } else {
            element.style.backgroundImage =
                `url("${url}")`;
        }

        element.classList.add("preview-ready");
    }

    function updateUnifiedAcquisitionPreview() {
        const count = [
            state.selectedFiles.a,
            state.selectedFiles.b
        ].filter(Boolean).length;

        $$("[data-image-count]").forEach(el => {
            el.textContent =
                `${count} / 2 images selected`;
        });

        $$("[data-ready-state]").forEach(el => {
            el.classList.toggle(
                "ready",
                count === 2
            );
        });

        const previewA = $("[data-preview='a']");
        const previewB = $("[data-preview='b']");

        if (previewA && state.selectedFiles.a) {
            renderImagePreview(
                state.selectedFiles.a,
                previewA
            );
        }

        if (previewB && state.selectedFiles.b) {
            renderImagePreview(
                state.selectedFiles.b,
                previewB
            );
        }
    }

    /* ---------------------------------------------------------
       ANALYSIS
       --------------------------------------------------------- */

    function initAnalysis() {
        $$("[data-analysis-form]").forEach(form => {
            form.addEventListener("submit", event => {
                event.preventDefault();
                runAnalysis(form);
            });
        });

        $$("[data-run-analysis]").forEach(button => {
            button.addEventListener("click", event => {
                event.preventDefault();

                const form =
                    button.closest("form") ||
                    $("[data-analysis-form]");

                if (form) {
                    runAnalysis(form);
                }
            });
        });
    }

    async function runAnalysis(form) {
        if (state.analysisRunning) return;

        const imageA =
            state.selectedFiles.a ||
            getImageFromInput(form, "a");

        const imageB =
            state.selectedFiles.b ||
            getImageFromInput(form, "b");

        if (!imageA || !imageB) {
            showToast(
                "Select two lunar images before running correspondence.",
                "error"
            );
            return;
        }

        if (!isImage(imageA) || !isImage(imageB)) {
            showToast(
                "Both selected files must be valid images.",
                "error"
            );
            return;
        }

        state.analysisRunning = true;

        const button =
            $("[data-run-analysis]", form) ||
            getSubmitButton(form);

        setButtonLoading(
            button,
            true,
            "ANALYSING..."
        );

        showAnalysisProgress();

        try {
            const formData = new FormData();

            formData.append("image_a", imageA);
            formData.append("image_b", imageB);

            /*
             * If the page contains optional research parameters,
             * include them without making them mandatory.
             */
            $$("[data-analysis-parameter]", form).forEach(field => {
                if (field.name && field.value !== "") {
                    formData.append(
                        field.name,
                        field.value
                    );
                }
            });

            const result = await api("/api/analyze", {
                method: "POST",
                body: formData
            });

            state.latestResult = result;

            if (result.public_id) {
                localStorage.setItem(
                    "lunarmatch_latest_id",
                    result.public_id
                );
            }

            try {
                localStorage.setItem(
                    "lunarmatch_latest_result",
                    JSON.stringify(result)
                );
            } catch (_) {
                // Storage is optional.
            }

            showAnalysisComplete(result);

            /*
             * If the backend returns a redirect, use it.
             * Otherwise render the result on the current page.
             */
            if (result.redirect) {
                setTimeout(() => {
                    window.location.href =
                        result.redirect;
                }, 400);
                return;
            }

            renderResult(result);

        } catch (error) {
            showToast(
                error.message ||
                    "Analysis failed. Please try again.",
                "error"
            );

            showAnalysisError(error.message);

        } finally {
            state.analysisRunning = false;

            setButtonLoading(
                button,
                false
            );
        }
    }

    function getImageFromInput(form, slot) {
        const selectors = [
            `input[type='file'][data-slot='${slot}']`,
            `input[type='file'][name='image_${slot}']`,
            `input[type='file'][name='image${slot.toUpperCase()}']`
        ];

        for (const selector of selectors) {
            const input = $(selector, form);

            if (input?.files?.[0]) {
                return input.files[0];
            }
        }

        return null;
    }

    function isImage(file) {
        return (
            file &&
            typeof file.type === "string" &&
            file.type.startsWith("image/")
        );
    }

    /* ---------------------------------------------------------
       PROGRESS UI
       --------------------------------------------------------- */

    function showAnalysisProgress() {
        $$("[data-analysis-progress]").forEach(el => {
            el.hidden = false;
            el.classList.add("active");
        });

        const stages = $$("[data-analysis-stage]");

        stages.forEach((stage, index) => {
            stage.classList.remove("active", "complete");

            setTimeout(() => {
                stage.classList.add("active");
            }, index * 450);
        });
    }

    function showAnalysisComplete() {
        $$("[data-analysis-stage]").forEach(stage => {
            stage.classList.remove("active");
            stage.classList.add("complete");
        });

        $$("[data-analysis-progress]").forEach(el => {
            el.classList.remove("active");
        });
    }

    function showAnalysisError(message) {
        $$("[data-analysis-progress]").forEach(el => {
            el.classList.remove("active");
        });

        const errorBoxes =
            $$("[data-analysis-error]");

        errorBoxes.forEach(el => {
            el.textContent =
                message ||
                "Analysis could not be completed.";

            el.hidden = false;
        });
    }

    /* ---------------------------------------------------------
       RESULTS
       --------------------------------------------------------- */

    function initResultActions() {
        $$("[data-load-result]").forEach(button => {
            button.addEventListener("click", async () => {
                const id =
                    button.dataset.loadResult;

                if (id) {
                    await loadResult(id);
                }
            });
        });

        $$("[data-download-report]").forEach(button => {
            button.addEventListener("click", async event => {
                event.preventDefault();

                const id =
                    button.dataset.downloadReport ||
                    state.latestResult?.public_id;

                if (!id) {
                    showToast(
                        "No analysis report is available.",
                        "error"
                    );
                    return;
                }

                await downloadReport(id);
            });
        });

        $$("[data-share-result]").forEach(button => {
            button.addEventListener("click", () => {
                shareResult(
                    button.dataset.shareResult ||
                    state.latestResult?.public_id
                );
            });
        });
    }

    async function loadResult(publicId) {
        if (!publicId) return;

        try {
            const result = await api(
                `/api/results?id=${encodeURIComponent(publicId)}`
            );

            state.latestResult = result;

            try {
                localStorage.setItem(
                    "lunarmatch_latest_result",
                    JSON.stringify(result)
                );
            } catch (_) {}

            renderResult(result);

        } catch (error) {
            showToast(
                error.message ||
                    "Unable to load this analysis.",
                "error"
            );
        }
    }

    function loadStoredResult() {
        const raw =
            localStorage.getItem(
                "lunarmatch_latest_result"
            );

        if (!raw) return;

        try {
            state.latestResult = JSON.parse(raw);
        } catch (_) {
            localStorage.removeItem(
                "lunarmatch_latest_result"
            );
        }
    }

    function renderResult(result) {
        if (!result || typeof result !== "object") {
            return;
        }

        const interpretation =
            result.interpretation ||
            result.result ||
            {};

        const validation =
            result.validation ||
            {};

        const evidence =
            result.evidence ||
            {};

        const score =
            Number(
                result.score ??
                result.evidence_score ??
                evidence.score ??
                0
            );

        const verified =
            Boolean(
                result.verified ??
                result.correspondence_verified ??
                false
            );

        setText(
            "[data-result-score]",
            formatNumber(score, 1)
        );

        setText(
            "[data-result-verdict]",
            interpretation.label ||
                (verified
                    ? "CORRESPONDENCE VERIFIED"
                    : "INCONCLUSIVE")
        );

        setText(
            "[data-result-summary]",
            interpretation.summary ||
                result.summary ||
                "Correspondence analysis completed."
        );

        setText(
            "[data-public-id]",
            result.public_id || "—"
        );

        setText(
            "[data-result-a-name]",
            result.image_a?.filename ||
                result.image_a_name ||
                result.image_a ||
                "Observation A"
        );

        setText(
            "[data-result-b-name]",
            result.image_b?.filename ||
                result.image_b_name ||
                result.image_b ||
                "Observation B"
        );

        setText(
            "[data-inlier-count]",
            result.inliers ??
                result.inlier_count ??
                evidence.inliers ??
                "—"
        );

        setText(
            "[data-inlier-ratio]",
            formatPercentage(
                result.inlier_ratio ??
                evidence.inlier_ratio
            )
        );

        setText(
            "[data-match-count]",
            result.good_matches ??
                result.match_count ??
                evidence.good_matches ??
                "—"
        );

        setText(
            "[data-result-confidence]",
            evidence.interpretation ||
                validation.overall ||
                "Evidence-based assessment"
        );

        renderValidation(validation);
        renderLocalization(
            result.localization ||
            validation.localization ||
            {}
        );

        renderEvidence(evidence);

        if (result.visualization_url) {
            $$("[data-match-visualization]").forEach(img => {
                img.src = result.visualization_url;
                img.hidden = false;
            });
        }

        $$("[data-result-container]").forEach(el => {
            el.hidden = false;
            el.classList.add("result-ready");
        });

        window.dispatchEvent(
            new CustomEvent("lunarmatch:result", {
                detail: result
            })
        );
    }

    function renderValidation(validation) {
        if (!validation) return;

        const items = [
            ["coordinate", "coordinate"],
            ["instrument", "instrument"],
            ["mission", "mission"],
            ["projection", "projection"],
            ["reference", "reference"]
        ];

        items.forEach(([key, name]) => {
            const item =
                validation[name];

            const target =
                $(`[data-validation='${key}']`);

            if (!target) return;

            if (typeof item === "object") {
                const status =
                    item.status ||
                    item.result ||
                    item.message ||
                    "NOT ESTABLISHED";

                target.textContent = status;

                target.dataset.status =
                    normalizeStatus(status);
            } else {
                target.textContent =
                    item || "NOT ESTABLISHED";
            }
        });

        const warnings =
            validation.warnings ||
            [];

        const warningContainer =
            $("[data-validation-warnings]");

        if (warningContainer) {
            warningContainer.innerHTML = "";

            if (!warnings.length) {
                warningContainer.hidden = true;
            } else {
                warningContainer.hidden = false;

                warnings.forEach(warning => {
                    const item =
                        document.createElement("li");

                    item.textContent =
                        typeof warning === "string"
                            ? warning
                            : JSON.stringify(warning);

                    warningContainer.appendChild(item);
                });
            }
        }
    }

    function renderLocalization(localization) {
        if (!localization) return;

        const lat =
            localization.latitude ??
            localization.lat;

        const lon =
            localization.longitude ??
            localization.lon ??
            localization.lng;

        setText(
            "[data-latitude]",
            lat !== null &&
            lat !== undefined
                ? formatCoordinate(lat)
                : "NOT AVAILABLE"
        );

        setText(
            "[data-longitude]",
            lon !== null &&
            lon !== undefined
                ? formatCoordinate(lon)
                : "NOT AVAILABLE"
        );

        setText(
            "[data-localization-status]",
            localization.status ||
                localization.message ||
                (
                    lat !== null &&
                    lat !== undefined &&
                    lon !== null &&
                    lon !== undefined
                        ? "Metadata-derived"
                        : "NOT AVAILABLE"
                )
        );

        const note =
            $("[data-localization-note]");

        if (note) {
            note.textContent =
                localization.note ||
                "Coordinates are displayed only when supported by legitimate metadata or validated reference information.";
        }
    }

    function renderEvidence(evidence) {
        if (!evidence) return;

        const fields = {
            correspondence:
                evidence.correspondence ??
                evidence.correspondence_score,

            geometric:
                evidence.geometric ??
                evidence.geometric_consistency,

            inliers:
                evidence.inlier_count ??
                evidence.inliers,

            quality:
                evidence.image_quality ??
                evidence.quality
        };

        Object.entries(fields).forEach(
            ([key, value]) => {
                if (
                    value === null ||
                    value === undefined
                ) {
                    return;
                }

                setText(
                    `[data-evidence='${key}']`,
                    formatNumber(value, 1)
                );
            }
        );

        const note =
            $("[data-evidence-note]");

        if (note) {
            note.textContent =
                "The evidence score is a transparent engineering score, not a statistical probability of correctness.";
        }
    }

    /* ---------------------------------------------------------
       REPORT DOWNLOAD
       --------------------------------------------------------- */

    async function downloadReport(publicId) {
        if (!state.user) {
            showToast(
                "Sign in to download the full scientific report.",
                "error"
            );
            return;
        }

        try {
            showToast(
                "Preparing your PDF report...",
                "info"
            );

            const response = await fetch(
                `/api/report/${encodeURIComponent(publicId)}`,
                {
                    credentials: "same-origin"
                }
            );

            if (!response.ok) {
                let message =
                    "The report could not be generated.";

                try {
                    const data =
                        await response.json();

                    if (data.error) {
                        message = data.error;
                    }
                } catch (_) {}

                throw new Error(message);
            }

            const blob =
                await response.blob();

            const url =
                URL.createObjectURL(blob);

            const anchor =
                document.createElement("a");

            anchor.href = url;
            anchor.download =
                `LUNARMATCH-${publicId}.pdf`;

            document.body.appendChild(anchor);
            anchor.click();
            anchor.remove();

            setTimeout(() => {
                URL.revokeObjectURL(url);
            }, 1500);

            showToast(
                "PDF report generated.",
                "success"
            );

        } catch (error) {
            showToast(
                error.message,
                "error"
            );
        }
    }

    /* ---------------------------------------------------------
       FEEDBACK
       --------------------------------------------------------- */

    function initFeedback() {
        $$("[data-rating]").forEach(button => {
            button.addEventListener("click", () => {
                const rating =
                    button.dataset.rating;

                $$("[data-rating]").forEach(item => {
                    item.classList.toggle(
                        "selected",
                        item.dataset.rating === rating
                    );
                });

                const hidden =
                    $(
                        "input[name='rating']",
                        button.closest("form") ||
                        document
                    );

                if (hidden) {
                    hidden.value = rating;
                }
            });
        });
    }

    async function handleFeedback(form) {
        const button = getSubmitButton(form);

        setButtonLoading(
            button,
            true,
            "SUBMITTING..."
        );

        try {
            const data =
                collectFormData(form);

            if (!data.message) {
                throw new Error(
                    "Please enter your feedback."
                );
            }

            const result =
                await api("/api/feedback", {
                    method: "POST",
                    body: data
                });

            showFormMessage(
                form,
                result.message ||
                    "Thank you for your feedback.",
                "success"
            );

            form.reset();

            $$("[data-rating]", form).forEach(
                item => item.classList.remove("selected")
            );

        } catch (error) {
            showFormMessage(
                form,
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

    /* ---------------------------------------------------------
       STRESS TESTING
       --------------------------------------------------------- */

    function initStressTesting() {
        $$("[data-stress-form]").forEach(form => {
            form.addEventListener("submit", event => {
                event.preventDefault();
                runStressTest(form);
            });
        });
    }

    async function runStressTest(form) {
        const imageInput =
            $("input[type='file']", form);

        const file =
            imageInput?.files?.[0];

        if (!file) {
            showToast(
                "Select a reference image for the stress test.",
                "error"
            );
            return;
        }

        const button =
            getSubmitButton(form);

        setButtonLoading(
            button,
            true,
            "TESTING..."
        );

        try {
            const formData =
                new FormData(form);

            /*
             * Ensure the backend receives the expected
             * field name even if the HTML uses a custom one.
             */
            if (!formData.has("image")) {
                formData.append("image", file);
            }

            const result =
                await api("/api/stress", {
                    method: "POST",
                    body: formData
                });

            renderStressResult(result);

            showToast(
                "Stress test completed.",
                "success"
            );

        } catch (error) {
            showToast(
                error.message ||
                    "Stress testing failed.",
                "error"
            );
        } finally {
            setButtonLoading(
                button,
                false
            );
        }
    }

    function renderStressResult(result) {
        const container =
            $("[data-stress-results]");

        if (!container) return;

        container.hidden = false;

        const rows =
            result.tests ||
            result.results ||
            [];

        const body =
            $("[data-stress-table-body]", container);

        if (body) {
            body.innerHTML = "";

            if (Array.isArray(rows)) {
                rows.forEach(test => {
                    const tr =
                        document.createElement("tr");

                    const name =
                        document.createElement("td");

                    const score =
                        document.createElement("td");

                    const status =
                        document.createElement("td");

                    name.textContent =
                        test.name ||
                        test.type ||
                        "Test";

                    score.textContent =
                        test.score !== undefined
                            ? formatNumber(test.score, 1)
                            : "—";

                    status.textContent =
                        test.status ||
                        test.interpretation ||
                        "—";

                    tr.append(
                        name,
                        score,
                        status
                    );

                    body.appendChild(tr);
                });
            }
        }

        setText(
            "[data-stress-summary]",
            result.summary ||
                result.message ||
                "Stress test completed."
        );
    }

    /* ---------------------------------------------------------
       SHARE
       --------------------------------------------------------- */

    async function shareResult(publicId) {
        if (!publicId) {
            showToast(
                "No analysis is available to share.",
                "error"
            );
            return;
        }

        const url =
            `${window.location.origin}/results?id=${encodeURIComponent(publicId)}`;

        try {
            if (
                navigator.share &&
                window.isSecureContext
            ) {
                await navigator.share({
                    title: "LUNARMATCH Analysis",
                    text:
                        "LUNARMATCH lunar image correspondence analysis",
                    url
                });

                return;
            }

            await navigator.clipboard.writeText(url);

            showToast(
                "Analysis link copied to clipboard.",
                "success"
            );

        } catch (error) {
            if (error?.name === "AbortError") {
                return;
            }

            showToast(
                "Unable to share the analysis link.",
                "error"
            );
        }
    }

    /* ---------------------------------------------------------
       NAVIGATION
       --------------------------------------------------------- */

    function initNavigation() {
        const currentPath =
            window.location.pathname;

        $$("a[href]").forEach(link => {
            const href =
                link.getAttribute("href");

            if (
                !href ||
                href.startsWith("#") ||
                href.startsWith("http") ||
                href.startsWith("mailto:")
            ) {
                return;
            }

            try {
                const linkPath =
                    new URL(
                        href,
                        window.location.origin
                    ).pathname;

                if (
                    linkPath === currentPath ||
                    (
                        linkPath !== "/" &&
                        currentPath.startsWith(linkPath)
                    )
                ) {
                    link.classList.add("active");
                    link.setAttribute(
                        "aria-current",
                        "page"
                    );
                }
            } catch (_) {}
        });
    }

    function initMobileNavigation() {
        const toggle =
            $("[data-mobile-menu-toggle]");

        const menu =
            $("[data-mobile-menu]");

        if (!toggle || !menu) return;

        toggle.addEventListener("click", () => {
            const open =
                menu.classList.toggle("open");

            toggle.setAttribute(
                "aria-expanded",
                String(open)
            );

            document.body.classList.toggle(
                "menu-open",
                open
            );
        });

        $$("a", menu).forEach(link => {
            link.addEventListener("click", () => {
                menu.classList.remove("open");

                toggle.setAttribute(
                    "aria-expanded",
                    "false"
                );

                document.body.classList.remove(
                    "menu-open"
                );
            });
        });
    }

    /* ---------------------------------------------------------
       SCROLL REVEAL
       --------------------------------------------------------- */

    function initRevealAnimations() {
        const elements =
            $$("[data-reveal]");

        if (!elements.length) return;

        if (!("IntersectionObserver" in window)) {
            elements.forEach(el => {
                el.classList.add("revealed");
            });

            return;
        }

        const observer =
            new IntersectionObserver(
                entries => {
                    entries.forEach(entry => {
                        if (!entry.isIntersecting) {
                            return;
                        }

                        entry.target.classList.add(
                            "revealed"
                        );

                        observer.unobserve(
                            entry.target
                        );
                    });
                },
                {
                    threshold: 0.12,
                    rootMargin: "0px 0px -50px 0px"
                }
            );

        elements.forEach(el =>
            observer.observe(el)
        );
    }

    /* ---------------------------------------------------------
       3D CARD INTERACTION
       --------------------------------------------------------- */

    function initTiltCards() {
        if (window.matchMedia(
            "(prefers-reduced-motion: reduce)"
        ).matches) {
            return;
        }

        $$("[data-tilt]").forEach(card => {
            card.addEventListener("pointermove", event => {
                const rect =
                    card.getBoundingClientRect();

                const x =
                    (event.clientX - rect.left) /
                    rect.width;

                const y =
                    (event.clientY - rect.top) /
                    rect.height;

                const rotateX =
                    (0.5 - y) * 7;

                const rotateY =
                    (x - 0.5) * 7;

                card.style.transform =
                    `perspective(900px) rotateX(${rotateX}deg) rotateY(${rotateY}deg) translateY(-2px)`;
            });

            card.addEventListener("pointerleave", () => {
                card.style.transform = "";
            });
        });
    }

    /* ---------------------------------------------------------
       SPACE CANVAS
       --------------------------------------------------------- */

    function initSpaceCanvas() {
        const canvas =
            $("#spaceCanvas");

        if (!canvas) return;

        const context =
            canvas.getContext("2d");

        if (!context) return;

        const reducedMotion =
            window.matchMedia(
                "(prefers-reduced-motion: reduce)"
            ).matches;

        let width = 0;
        let height = 0;
        let stars = [];

        function resize() {
            const ratio =
                Math.min(
                    window.devicePixelRatio || 1,
                    2
                );

            width =
                canvas.clientWidth;

            height =
                canvas.clientHeight;

            canvas.width =
                Math.floor(width * ratio);

            canvas.height =
                Math.floor(height * ratio);

            context.setTransform(
                ratio,
                0,
                0,
                ratio,
                0,
                0
            );

            createStars();
        }

        function createStars() {
            const count =
                Math.min(
                    180,
                    Math.max(
                        70,
                        Math.floor(
                            (width * height) /
                            12000
                        )
                    )
                );

            stars =
                Array.from(
                    { length: count },
                    () => ({
                        x: Math.random() * width,
                        y: Math.random() * height,
                        radius:
                            Math.random() * 1.5 + 0.2,
                        alpha:
                            Math.random() * 0.7 + 0.15,
                        speed:
                            Math.random() * 0.18 + 0.03
                    })
                );
        }

        function draw(time = 0) {
            context.clearRect(
                0,
                0,
                width,
                height
            );

            stars.forEach(star => {
                if (!reducedMotion) {
                    star.y += star.speed;

                    if (star.y > height) {
                        star.y = 0;
                        star.x =
                            Math.random() * width;
                    }
                }

                const pulse =
                    reducedMotion
                        ? 1
                        : 0.75 +
                          Math.sin(
                              time * 0.001 +
                              star.x
                          ) *
                          0.2;

                context.globalAlpha =
                    Math.max(
                        0.05,
                        star.alpha * pulse
                    );

                context.beginPath();

                context.arc(
                    star.x,
                    star.y,
                    star.radius,
                    0,
                    Math.PI * 2
                );

                context.fill();
            });

            context.globalAlpha = 1;

            if (!reducedMotion) {
                requestAnimationFrame(draw);
            }
        }

        resize();

        window.addEventListener(
            "resize",
            resize
        );

        draw();
    }

    /* ---------------------------------------------------------
       TOAST SYSTEM
       --------------------------------------------------------- */

    function showToast(message, type = "info") {
        let container =
            $("#toast-container");

        if (!container) {
            container =
                document.createElement("div");

            container.id =
                "toast-container";

            container.setAttribute(
                "aria-live",
                "polite"
            );

            document.body.appendChild(
                container
            );
        }

        const toast =
            document.createElement("div");

        toast.className =
            `toast toast-${type}`;

        toast.setAttribute(
            "role",
            type === "error"
                ? "alert"
                : "status"
        );

        toast.textContent = message;

        container.appendChild(toast);

        requestAnimationFrame(() => {
            toast.classList.add("show");
        });

        setTimeout(() => {
            toast.classList.remove("show");

            setTimeout(() => {
                toast.remove();
            }, 300);
        }, 4200);
    }

    /* ---------------------------------------------------------
       UTILITY HELPERS
       --------------------------------------------------------- */

    function setText(selector, value) {
        $$(selector).forEach(el => {
            el.textContent =
                value === null ||
                value === undefined ||
                value === ""
                    ? "—"
                    : String(value);
        });
    }

    function formatNumber(value, decimals = 1) {
        const number =
            Number(value);

        if (!Number.isFinite(number)) {
            return "—";
        }

        return number.toFixed(decimals);
    }

    function formatPercentage(value) {
        const number =
            Number(value);

        if (!Number.isFinite(number)) {
            return "—";
        }

        /*
         * Backend values may be 0.25 or 25.
         * Convert fractional ratios to percentages.
         */
        const percentage =
            number <= 1
                ? number * 100
                : number;

        return `${percentage.toFixed(1)}%`;
    }

    function formatCoordinate(value) {
        const number =
            Number(value);

        if (!Number.isFinite(number)) {
            return "NOT AVAILABLE";
        }

        return number.toFixed(6);
    }

    function normalizeStatus(value) {
        const text =
            String(value || "").toLowerCase();

        if (
            text.includes("valid") ||
            text.includes("confirmed") ||
            text.includes("established") ||
            text.includes("available")
        ) {
            return "positive";
        }

        if (
            text.includes("warning") ||
            text.includes("partial") ||
            text.includes("limited")
        ) {
            return "warning";
        }

        return "neutral";
    }

    /* ---------------------------------------------------------
       KEYBOARD / ACCESSIBILITY
       --------------------------------------------------------- */

    document.addEventListener(
        "keydown",
        event => {
            if (event.key === "Escape") {
                const menu =
                    $("[data-mobile-menu]");

                const toggle =
                    $("[data-mobile-menu-toggle]");

                if (menu) {
                    menu.classList.remove("open");
                }

                if (toggle) {
                    toggle.setAttribute(
                        "aria-expanded",
                        "false"
                    );
                }

                document.body.classList.remove(
                    "menu-open"
                );
            }
        }
    );

    /* ---------------------------------------------------------
       GLOBAL EXPORT
       Useful for HTML buttons and debugging.
       --------------------------------------------------------- */

    window.LUNARMATCH = {
        state,

        runAnalysis,
        loadResult,
        downloadReport,
        shareResult,
        showToast,

        getUser: () => state.user,

        getLatestResult: () =>
            state.latestResult
    };

})();
```
