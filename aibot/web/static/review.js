// CV & application review demo: file upload or pasted text → POST /v1/review.
// The page and the review are available in Finnish and English.
(function () {
  "use strict";

  const config = JSON.parse(document.getElementById("review-config").textContent);
  const ALLOWED_EXTENSIONS = [".pdf", ".doc", ".docx"];
  const LANG_STORAGE = "aibot.lang";
  const LANGUAGES = ["fi", "en"];

  const STRINGS = {
    en: {
      pageTitle: "CV & application review",
      navDocs: "API docs",
      title: "CV & application review",
      lead: "Upload a CV or job application, or paste its text. The AI rates it from 0 to 5 stars and lists its strengths and what to improve.",
      tabFile: "Upload file",
      tabText: "Paste text",
      dropTitle: "Drag and drop a file here",
      dropOr: "or",
      dropChoose: "choose a file",
      dropTypes: "PDF, DOC or DOCX, up to {mb} MB",
      removeFile: "Remove file",
      textLabel: "Document text",
      textPlaceholder: "Paste the CV or application text here…",
      chars: "{count} / {max} characters",
      kindLabel: "Document type",
      kind_cv: "CV",
      "kind_cover-letter": "Job application",
      reviewLanguage: "The review is written in {language}.",
      language_fi: "Finnish",
      language_en: "English",
      submit: "Review",
      reviewing: "Reviewing…",
      reviewingHint: "Reviewing… this usually takes 5–30 seconds.",
      privacy: "The document is sent to an AI service for the review and is not stored here. Avoid uploading sensitive personal data you don't want to share.",
      summary: "Summary",
      strengths: "Strengths",
      weaknesses: "To improve",
      again: "Review another",
      starsLabel: "{count} out of 5 stars",
      errType: "Unsupported file type. Use a PDF, DOC or DOCX file, or paste the text instead.",
      errSize: "The file is too large. The limit is {mb} MB.",
      errNoFile: "Choose or drop a file first.",
      errShortText: "Paste the full text of the CV or application (at least 50 characters).",
      err401: "Reviews are not available on this page right now.",
      err403: "This page is not allowed to use the API.",
      err413: "The document is too large.",
      err429: "The review limit has been reached.",
      err429Wait: "The review limit has been reached. Try again in {wait}.",
      err502: "The AI service could not finish the review. Please try again.",
      err503: "The AI service is not available right now.",
      errOther: "Something went wrong (HTTP {status}).",
      errNetwork: "Could not reach the service. Check your connection and try again.",
      seconds: "{n} seconds",
      minutes: "{n} minutes",
      hours: "{n} hours",
    },
    fi: {
      pageTitle: "CV- ja hakemusarvio",
      navDocs: "API-dokumentaatio",
      title: "CV- ja hakemusarvio",
      lead: "Lataa CV tai työhakemus tai liitä sen teksti. Tekoäly arvioi sen asteikolla 0–5 tähteä ja kertoo vahvuudet ja kehityskohteet.",
      tabFile: "Lataa tiedosto",
      tabText: "Liitä teksti",
      dropTitle: "Vedä ja pudota tiedosto tähän",
      dropOr: "tai",
      dropChoose: "valitse tiedosto",
      dropTypes: "PDF, DOC tai DOCX, enintään {mb} Mt",
      removeFile: "Poista tiedosto",
      textLabel: "Asiakirjan teksti",
      textPlaceholder: "Liitä CV:n tai hakemuksen teksti tähän…",
      chars: "{count} / {max} merkkiä",
      kindLabel: "Asiakirjan tyyppi",
      kind_cv: "CV (ansioluettelo)",
      "kind_cover-letter": "Työhakemus",
      reviewLanguage: "Arvio kirjoitetaan {language}.",
      language_fi: "suomeksi",
      language_en: "englanniksi",
      submit: "Arvioi",
      reviewing: "Arvioidaan…",
      reviewingHint: "Arvioidaan… tämä kestää yleensä 5–30 sekuntia.",
      privacy: "Asiakirja lähetetään arvioitavaksi tekoälypalvelulle, eikä sitä tallenneta tänne. Älä lataa arkaluonteisia henkilötietoja, joita et halua jakaa.",
      summary: "Yhteenveto",
      strengths: "Vahvuudet",
      weaknesses: "Kehityskohteet",
      again: "Arvioi toinen",
      starsLabel: "{count}/5 tähteä",
      errType: "Tiedostotyyppiä ei tueta. Käytä PDF-, DOC- tai DOCX-tiedostoa tai liitä teksti.",
      errSize: "Tiedosto on liian suuri. Enimmäiskoko on {mb} Mt.",
      errNoFile: "Valitse tai pudota ensin tiedosto.",
      errShortText: "Liitä CV:n tai hakemuksen koko teksti (vähintään 50 merkkiä).",
      err401: "Arviointi ei ole tällä sivulla juuri nyt käytettävissä.",
      err403: "Tällä sivulla ei ole oikeutta käyttää rajapintaa.",
      err413: "Asiakirja on liian suuri.",
      err429: "Arvioiden enimmäismäärä on täynnä.",
      err429Wait: "Arvioiden enimmäismäärä on täynnä. Yritä uudelleen {wait} kuluttua.",
      err502: "Tekoälypalvelu ei saanut arviota valmiiksi. Yritä uudelleen.",
      err503: "Tekoälypalvelu ei ole juuri nyt käytettävissä.",
      errOther: "Jokin meni vikaan (HTTP {status}).",
      errNetwork: "Palveluun ei saatu yhteyttä. Tarkista verkkoyhteys ja yritä uudelleen.",
      seconds: "{n} sekunnin",
      minutes: "{n} minuutin",
      hours: "{n} tunnin",
    },
  };

  const $ = (id) => document.getElementById(id);
  const form = $("review-form");
  const tabs = { file: $("tab-file"), text: $("tab-text") };
  const panels = { file: $("panel-file"), text: $("panel-text") };
  const dropzone = $("dropzone");
  const fileInput = $("file-input");
  const fileChip = $("file-chip");
  const textInput = $("text-input");
  const kindSelect = $("kind");
  const errorBox = $("form-error");
  const submitButton = $("submit-button");
  const submitHint = $("submit-hint");
  const result = $("result");

  let lang = "en";
  let mode = "file";
  let selectedFile = null;
  let loading = false;
  let lastResult = null;
  let lastError = null; // { key, vars, detail } so it can be re-translated

  // ── Translation ─────────────────────────────────────────
  function t(key, vars) {
    let text = (STRINGS[lang] && STRINGS[lang][key]) || STRINGS.en[key] || key;
    for (const [name, value] of Object.entries(vars || {})) {
      text = text.split("{" + name + "}").join(String(value));
    }
    return text;
  }

  function pickInitialLanguage() {
    const fromUrl = new URLSearchParams(location.search).get("lang");
    if (LANGUAGES.includes(fromUrl)) return fromUrl;
    try {
      const saved = localStorage.getItem(LANG_STORAGE);
      if (LANGUAGES.includes(saved)) return saved;
    } catch (error) { /* storage unavailable */ }
    const browser = (navigator.languages || [navigator.language || ""]).map((l) => l.toLowerCase());
    return browser.some((l) => l.startsWith("fi")) ? "fi" : "en";
  }

  function setLanguage(next) {
    lang = next;
    document.documentElement.lang = lang;
    document.title = t("pageTitle") + " · " + config.appName;
    try { localStorage.setItem(LANG_STORAGE, lang); } catch (error) { /* ignore */ }

    document.querySelectorAll("[data-lang]").forEach((button) => {
      button.setAttribute("aria-pressed", String(button.dataset.lang === lang));
    });
    document.querySelectorAll("[data-i18n]").forEach((el) => {
      el.textContent = t(el.dataset.i18n, { mb: config.maxUploadMb });
    });
    document.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
      el.placeholder = t(el.dataset.i18nPlaceholder);
    });
    document.querySelectorAll("[data-i18n-aria-label]").forEach((el) => {
      el.setAttribute("aria-label", t(el.dataset.i18nAriaLabel));
    });

    renderKinds();
    updateCharCount();
    setLoading(loading);
    if (lastError) showError(lastError.key, lastError.vars, lastError.detail);
    if (lastResult) renderResult(lastResult);
  }

  document.querySelectorAll("[data-lang]").forEach((button) => {
    button.addEventListener("click", () => setLanguage(button.dataset.lang));
  });

  // ── Document types and review language ──────────────────
  // Rubric ids look like "<kind>-<language>", e.g. "cv-fi" or "cover-letter-en".
  const kinds = [];
  const rubricsByKind = {};
  for (const rubric of config.rubrics) {
    const suffix = "-" + rubric.language;
    const kind = rubric.id.endsWith(suffix) ? rubric.id.slice(0, -suffix.length) : rubric.id;
    if (!rubricsByKind[kind]) {
      rubricsByKind[kind] = {};
      kinds.push(kind);
    }
    rubricsByKind[kind][rubric.language] = rubric;
  }
  kinds.sort((a, b) => (a === "cv" ? -1 : b === "cv" ? 1 : 0));

  function kindLabel(kind) {
    const key = "kind_" + kind;
    if ((STRINGS[lang] && STRINGS[lang][key]) || STRINGS.en[key]) return t(key);
    const any = Object.values(rubricsByKind[kind])[0];
    return any ? any.name : kind;
  }

  function renderKinds() {
    const current = kindSelect.value || kinds[0];
    kindSelect.replaceChildren(...kinds.map((kind) => new Option(kindLabel(kind), kind)));
    kindSelect.value = current;
    updateReviewLanguage();
  }

  function selectedRubric() {
    const options = rubricsByKind[kindSelect.value] || {};
    return options[lang] || Object.values(options)[0];
  }

  function updateReviewLanguage() {
    const rubric = selectedRubric();
    const language = rubric ? t("language_" + rubric.language) : "";
    $("review-language").textContent = rubric ? t("reviewLanguage", { language }) : "";
  }

  kindSelect.addEventListener("change", updateReviewLanguage);

  // ── Tabs ────────────────────────────────────────────────
  function selectTab(name, focus) {
    mode = name;
    for (const key of Object.keys(tabs)) {
      const active = key === name;
      tabs[key].setAttribute("aria-selected", String(active));
      tabs[key].tabIndex = active ? 0 : -1;
      panels[key].hidden = !active;
    }
    if (focus) tabs[name].focus();
    hideError();
  }

  tabs.file.addEventListener("click", () => selectTab("file"));
  tabs.text.addEventListener("click", () => selectTab("text"));
  for (const tab of Object.values(tabs)) {
    tab.addEventListener("keydown", (event) => {
      if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
        selectTab(mode === "file" ? "text" : "file", true);
        event.preventDefault();
      }
    });
  }

  // ── File selection and drag and drop ────────────────────
  function formatSize(bytes) {
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 * 1024) return Math.round(bytes / 1024) + " KB";
    return (bytes / (1024 * 1024)).toFixed(1) + " MB";
  }

  function setFile(file) {
    hideError();
    if (!file) return;
    const name = file.name.toLowerCase();
    if (!ALLOWED_EXTENSIONS.some((ext) => name.endsWith(ext))) {
      showError("errType");
      return;
    }
    if (file.size > config.maxUploadMb * 1024 * 1024) {
      showError("errSize", { mb: config.maxUploadMb });
      return;
    }
    selectedFile = file;
    $("file-name").textContent = file.name;
    $("file-size").textContent = formatSize(file.size);
    fileChip.hidden = false;
  }

  function clearFile() {
    selectedFile = null;
    fileInput.value = "";
    fileChip.hidden = true;
  }

  fileInput.addEventListener("change", () => setFile(fileInput.files[0]));
  $("file-clear").addEventListener("click", clearFile);

  ["dragenter", "dragover"].forEach((type) =>
    dropzone.addEventListener(type, (event) => {
      event.preventDefault();
      dropzone.classList.add("dragging");
    })
  );
  ["dragleave", "dragend", "drop"].forEach((type) =>
    dropzone.addEventListener(type, () => dropzone.classList.remove("dragging"))
  );
  dropzone.addEventListener("drop", (event) => {
    event.preventDefault();
    const file = event.dataTransfer && event.dataTransfer.files[0];
    if (file) setFile(file);
  });
  // A file dropped next to the drop zone should not open in the browser.
  window.addEventListener("dragover", (event) => event.preventDefault());
  window.addEventListener("drop", (event) => event.preventDefault());

  // ── Text ────────────────────────────────────────────────
  function updateCharCount() {
    const locale = lang === "fi" ? "fi-FI" : "en-US";
    $("char-count").textContent = t("chars", {
      count: textInput.value.length.toLocaleString(locale),
      max: config.maxTextChars.toLocaleString(locale),
    });
  }
  textInput.addEventListener("input", updateCharCount);

  // ── Errors ──────────────────────────────────────────────
  function showError(key, vars, detail) {
    lastError = { key, vars, detail };
    errorBox.textContent = t(key, vars) + (detail ? " (" + detail + ")" : "");
    errorBox.hidden = false;
  }

  function hideError() {
    lastError = null;
    errorBox.hidden = true;
    errorBox.textContent = "";
  }

  function waitText(seconds) {
    if (seconds < 90) return t("seconds", { n: seconds });
    if (seconds < 5400) return t("minutes", { n: Math.round(seconds / 60) });
    return t("hours", { n: Math.round(seconds / 3600) });
  }

  async function showResponseError(response) {
    let detail = "";
    try {
      const body = await response.json();
      detail = typeof body.detail === "string" ? body.detail
        : Array.isArray(body.detail) ? body.detail.map((d) => d.msg).join(" ") : "";
    } catch (error) { /* not JSON */ }

    switch (response.status) {
      case 401:
        return showError("err401");
      case 403:
        return showError("err403", null, detail);
      case 413:
        return showError("err413", null, detail);
      case 429: {
        const wait = parseInt(response.headers.get("Retry-After") || "", 10);
        return wait ? showError("err429Wait", { wait: waitText(wait) }) : showError("err429");
      }
      // Server errors can quote the AI provider, model included, so their detail stays hidden.
      case 502:
        return showError("err502");
      case 503:
        return showError("err503");
      default:
        return showError("errOther", { status: response.status }, response.status < 500 ? detail : "");
    }
  }

  // ── Submit ──────────────────────────────────────────────
  function setLoading(value) {
    loading = value;
    submitButton.disabled = value;
    submitButton.replaceChildren();
    if (value) {
      const spinner = document.createElement("span");
      spinner.className = "spinner";
      spinner.setAttribute("aria-hidden", "true");
      submitButton.append(spinner, t("reviewing"));
    } else {
      submitButton.append(t("submit"));
    }
    submitHint.hidden = !value;
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    hideError();

    const rubric = selectedRubric();
    const data = new FormData();
    data.append("rubric", rubric ? rubric.id : "");
    if (mode === "file") {
      if (!selectedFile) return showError("errNoFile");
      data.append("file", selectedFile, selectedFile.name);
    } else {
      const text = textInput.value.trim();
      if (text.length < 50) {
        textInput.focus();
        return showError("errShortText");
      }
      data.append("text", text);
    }

    setLoading(true);
    try {
      const response = await fetch("/v1/review", { method: "POST", body: data });
      if (!response.ok) {
        await showResponseError(response);
        return;
      }
      lastResult = await response.json();
      renderResult(lastResult);
      result.hidden = false;
      result.scrollIntoView({ behavior: "smooth", block: "start" });
      result.focus({ preventScroll: true });
    } catch (error) {
      showError("errNetwork");
    } finally {
      setLoading(false);
    }
  });

  // ── Result ──────────────────────────────────────────────
  const STAR_PATH = "M12 2.5l2.9 6.1 6.6.8-4.9 4.6 1.3 6.6L12 17.3l-5.9 3.3 1.3-6.6-4.9-4.6 6.6-.8z";
  const SVG_NS = "http://www.w3.org/2000/svg";

  function renderStars(count) {
    const stars = $("stars");
    stars.replaceChildren();
    stars.setAttribute("aria-label", t("starsLabel", { count }));
    for (let i = 1; i <= 5; i++) {
      const svg = document.createElementNS(SVG_NS, "svg");
      svg.setAttribute("viewBox", "0 0 24 24");
      svg.setAttribute("aria-hidden", "true");
      if (i <= count) {
        svg.classList.add("on");
        svg.style.animationDelay = (i - 1) * 90 + "ms";
      }
      const path = document.createElementNS(SVG_NS, "path");
      path.setAttribute("d", STAR_PATH);
      svg.append(path);
      stars.append(svg);
    }
  }

  function fillList(id, items) {
    const list = $(id);
    list.replaceChildren();
    for (const item of items && items.length ? items : ["—"]) {
      const li = document.createElement("li");
      li.textContent = item;
      list.append(li);
    }
  }

  function renderResult(data) {
    const stars = Math.max(0, Math.min(5, Number(data.stars) || 0));
    renderStars(stars);

    const rating = $("rating");
    rating.textContent = data.rating_text || "";
    const score = document.createElement("small");
    score.textContent = stars + " / 5";
    rating.append(score);

    const kind = kinds.find((k) => Object.values(rubricsByKind[k]).some((r) => r.id === data.rubric));
    const parts = [kind ? kindLabel(kind) : data.rubric];
    if (data.language) parts.push(t("language_" + data.language));
    $("result-meta").textContent = parts.join(" · ");

    $("summary").textContent = data.summary || "—";
    fillList("strengths", data.strengths);
    fillList("weaknesses", data.weaknesses);
  }

  $("again").addEventListener("click", () => {
    result.hidden = true;
    lastResult = null;
    form.scrollIntoView({ behavior: "smooth", block: "start" });
  });

  setLanguage(pickInitialLanguage());
})();
