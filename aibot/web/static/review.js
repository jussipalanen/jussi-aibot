// Review demos: file uploads or pasted text → POST /v1/review, in Finnish and English.
// One script serves two pages, picked by `config.page`:
//   "document" (/demo/review)       CVs and job applications, one PDF, DOC or DOCX file
//   "code"     (/demo/code-review)  source code: several files, language detection and
//                                   suggested changes (current code → replacement)
(function () {
  "use strict";

  const config = JSON.parse(document.getElementById("review-config").textContent);
  const CODE_PAGE = config.page === "code";
  const DOCUMENT_EXTENSIONS = [".pdf", ".doc", ".docx"];
  const LANG_STORAGE = "aibot.lang";
  const LANGUAGES = ["fi", "en"];

  const STRINGS = {
    en: {
      pageTitle: "CV & application review",
      pageTitleCode: "Code review",
      navReview: "CV review",
      navCode: "Code review",
      navDocs: "API docs",
      title: "CV & application review",
      titleCode: "Code review",
      lead: "Upload a CV or job application, or paste its text. The AI rates it from 0 to 5 stars and lists its strengths and what to improve.",
      leadCode: "Upload source files or paste code. The language is detected automatically, and the AI rates the code from 0 to 5 stars and suggests changes: what to replace and what to use instead.",
      tabFile: "Upload file",
      tabText: "Paste text",
      tabFileCode: "Upload files",
      tabTextCode: "Paste code",
      dropTitle: "Drag and drop a file here",
      dropOr: "or",
      dropChoose: "choose a file",
      dropTypes: "PDF, DOC or DOCX, up to {mb} MB",
      dropTitleCode: "Drag and drop source files here",
      dropChooseCode: "choose files",
      dropTypesCode: "Up to {files} files in most programming languages, {mb} MB in total",
      removeFile: "Remove file",
      textLabel: "Document text",
      textPlaceholder: "Paste the CV or application text here…",
      textLabelCode: "Code",
      textPlaceholderCode: "Paste the code here…",
      detectedLanguage: "Detected language: {language}",
      unknownLanguage: "Language not recognised yet",
      chars: "{count} / {max} characters",
      kindLabel: "Document type",
      kind_cv: "CV",
      "kind_cover-letter": "Job application",
      "kind_code-review": "Code review",
      reviewLanguage: "The review is written in {language}.",
      language_fi: "Finnish",
      language_en: "English",
      submit: "Review",
      reviewing: "Reviewing…",
      reviewingHint: "Reviewing… this usually takes 5–30 seconds.",
      privacy: "The document is sent to an AI service for the review and is not stored here. Avoid uploading sensitive personal data you don't want to share.",
      privacyCode: "The code is sent to an AI service for the review and is not stored here. Don't include secrets such as passwords or API keys.",
      summary: "Summary",
      strengths: "Strengths",
      weaknesses: "To improve",
      again: "Review another",
      production: "Production readiness",
      verdict_ready: "Ready for production",
      verdict_needs_work: "Needs work first",
      verdict_not_ready: "Not ready",
      security: "Security risk",
      risk_none: "No known risks",
      risk_low: "Low",
      risk_medium: "Medium",
      risk_high: "High",
      risk_critical: "Critical",
      issueCount: "{count} issues found",
      issueCountOne: "1 issue found",
      noIssues: "No vulnerabilities found",
      securityIssues: "Security issues",
      suggestions: "Suggested changes",
      current: "Current",
      suggested: "Replace with",
      line: "line {n}",
      copy: "Copy",
      copied: "Copied",
      starsLabel: "{count} out of 5 stars",
      errType: "Unsupported file type. Use a PDF, DOC or DOCX file, or paste the text instead.",
      errSize: "The file is too large. The limit is {mb} MB.",
      errNoFile: "Choose or drop a file first.",
      errNoFileCode: "Choose or drop source files first.",
      errShortText: "Paste the full text of the CV or application (at least 50 characters).",
      errShortTextCode: "Paste some code first.",
      errTypeCode: "Unsupported file: {name}. Use source code files, such as .py, .js, .ts, .java or .go.",
      errTooManyFiles: "Choose at most {files} files.",
      err401: "Reviews are not available on this page right now.",
      err403: "This page is not allowed to use the API.",
      err413: "The document is too large.",
      err413Code: "The code is too large.",
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
      pageTitleCode: "Koodikatselmointi",
      navReview: "CV-arvio",
      navCode: "Koodikatselmointi",
      navDocs: "API-dokumentaatio",
      title: "CV- ja hakemusarvio",
      titleCode: "Koodikatselmointi",
      lead: "Lataa CV tai työhakemus tai liitä sen teksti. Tekoäly arvioi sen asteikolla 0–5 tähteä ja kertoo vahvuudet ja kehityskohteet.",
      leadCode: "Lataa lähdekooditiedostoja tai liitä koodi. Ohjelmointikieli tunnistetaan automaattisesti, ja tekoäly arvioi koodin asteikolla 0–5 tähteä ja ehdottaa muutoksia: mitä korvata ja millä.",
      tabFile: "Lataa tiedosto",
      tabText: "Liitä teksti",
      tabFileCode: "Lataa tiedostot",
      tabTextCode: "Liitä koodi",
      dropTitle: "Vedä ja pudota tiedosto tähän",
      dropOr: "tai",
      dropChoose: "valitse tiedosto",
      dropTypes: "PDF, DOC tai DOCX, enintään {mb} Mt",
      dropTitleCode: "Vedä ja pudota lähdekooditiedostot tähän",
      dropChooseCode: "valitse tiedostot",
      dropTypesCode: "Enintään {files} tiedostoa useimmilla ohjelmointikielillä, yhteensä {mb} Mt",
      removeFile: "Poista tiedosto",
      textLabel: "Asiakirjan teksti",
      textPlaceholder: "Liitä CV:n tai hakemuksen teksti tähän…",
      textLabelCode: "Koodi",
      textPlaceholderCode: "Liitä koodi tähän…",
      detectedLanguage: "Tunnistettu kieli: {language}",
      unknownLanguage: "Kieltä ei vielä tunnistettu",
      chars: "{count} / {max} merkkiä",
      kindLabel: "Asiakirjan tyyppi",
      kind_cv: "CV (ansioluettelo)",
      "kind_code-review": "Koodikatselmointi",
      "kind_cover-letter": "Työhakemus",
      reviewLanguage: "Arvio kirjoitetaan {language}.",
      language_fi: "suomeksi",
      language_en: "englanniksi",
      submit: "Arvioi",
      reviewing: "Arvioidaan…",
      reviewingHint: "Arvioidaan… tämä kestää yleensä 5–30 sekuntia.",
      privacy: "Asiakirja lähetetään arvioitavaksi tekoälypalvelulle, eikä sitä tallenneta tänne. Älä lataa arkaluonteisia henkilötietoja, joita et halua jakaa.",
      privacyCode: "Koodi lähetetään arvioitavaksi tekoälypalvelulle, eikä sitä tallenneta tänne. Älä lähetä salaisuuksia, kuten salasanoja tai API-avaimia.",
      summary: "Yhteenveto",
      strengths: "Vahvuudet",
      weaknesses: "Kehityskohteet",
      again: "Arvioi toinen",
      production: "Tuotantovalmius",
      verdict_ready: "Valmis tuotantoon",
      verdict_needs_work: "Vaatii korjauksia",
      verdict_not_ready: "Ei valmis",
      security: "Tietoturvariski",
      risk_none: "Ei tunnettuja riskejä",
      risk_low: "Matala",
      risk_medium: "Kohtalainen",
      risk_high: "Korkea",
      risk_critical: "Kriittinen",
      issueCount: "{count} ongelmaa löytyi",
      issueCountOne: "1 ongelma löytyi",
      noIssues: "Haavoittuvuuksia ei löytynyt",
      securityIssues: "Tietoturvaongelmat",
      suggestions: "Ehdotetut muutokset",
      current: "Nykyinen",
      suggested: "Korvaa tällä",
      line: "rivi {n}",
      copy: "Kopioi",
      copied: "Kopioitu",
      starsLabel: "{count}/5 tähteä",
      errType: "Tiedostotyyppiä ei tueta. Käytä PDF-, DOC- tai DOCX-tiedostoa tai liitä teksti.",
      errSize: "Tiedosto on liian suuri. Enimmäiskoko on {mb} Mt.",
      errNoFile: "Valitse tai pudota ensin tiedosto.",
      errNoFileCode: "Valitse tai pudota ensin lähdekooditiedostot.",
      errShortText: "Liitä CV:n tai hakemuksen koko teksti (vähintään 50 merkkiä).",
      errShortTextCode: "Liitä ensin koodia.",
      errTypeCode: "Tiedostoa ei tueta: {name}. Käytä lähdekooditiedostoja, kuten .py, .js, .ts, .java tai .go.",
      errTooManyFiles: "Valitse enintään {files} tiedostoa.",
      err401: "Arviointi ei ole tällä sivulla juuri nyt käytettävissä.",
      err403: "Tällä sivulla ei ole oikeutta käyttää rajapintaa.",
      err413: "Asiakirja on liian suuri.",
      err413Code: "Koodi on liian suuri.",
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
  const fileList = $("file-list");
  const chipTemplate = $("file-chip-template");
  const textInput = $("text-input");
  const kindSelect = $("kind");
  const errorBox = $("form-error");
  const submitButton = $("submit-button");
  const submitHint = $("submit-hint");
  const result = $("result");

  let lang = "en";
  let mode = "file";
  let selectedFiles = [];
  let loading = false;
  let lastResult = null;
  let lastError = null; // { key, vars, detail } so it can be re-translated

  // ── Translation ─────────────────────────────────────────
  // On the code page a "<key>Code" text, when there is one, replaces "<key>".
  function lookup(key) {
    return (STRINGS[lang] && STRINGS[lang][key]) || STRINGS.en[key];
  }

  function t(key, vars) {
    let text = (CODE_PAGE && lookup(key + "Code")) || lookup(key) || key;
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
    translatePage();
    renderKinds();
    renderFiles();
    updateCharCount();
    updateDetectedLanguage();
    setLoading(loading);
    if (lastError) showError(lastError.key, lastError.vars, lastError.detail);
    if (lastResult) renderResult(lastResult);
  }

  function translatePage() {
    const vars = { mb: config.maxUploadMb, files: config.maxCodeFiles };
    document.querySelectorAll("[data-page]").forEach((link) => {
      if (link.dataset.page === config.page) link.setAttribute("aria-current", "page");
    });
    document.querySelectorAll("[data-i18n]").forEach((el) => {
      el.textContent = t(el.dataset.i18n, vars);
    });
    document.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
      el.placeholder = t(el.dataset.i18nPlaceholder);
    });
    document.querySelectorAll("[data-i18n-aria-label]").forEach((el) => {
      el.setAttribute("aria-label", t(el.dataset.i18nAriaLabel));
    });
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
  // CVs first, then applications, then any other types.
  const KIND_ORDER = ["cv", "cover-letter"];
  const rank = (kind) => (KIND_ORDER.includes(kind) ? KIND_ORDER.indexOf(kind) : KIND_ORDER.length);
  kinds.sort((a, b) => rank(a) - rank(b));

  function kindLabel(kind) {
    const key = "kind_" + kind;
    if (lookup(key)) return t(key);
    const any = Object.values(rubricsByKind[kind])[0];
    return any ? any.name : kind;
  }

  function renderKinds() {
    const current = kindSelect.value || kinds[0];
    kindSelect.replaceChildren(...kinds.map((kind) => new Option(kindLabel(kind), kind)));
    kindSelect.value = current;
    // With one type (e.g. code review) there is nothing to choose; only the review language shows.
    kindSelect.hidden = $("kind-label").hidden = kinds.length < 2;
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

  kindSelect.addEventListener("change", () => {
    hideError();
    updateReviewLanguage();
  });

  // ── Programming language detection (code page) ──────────
  // The same rules as aibot/review/languages.py, sent in the page config, so the language
  // shown here matches the one in the review result. File names decide first.
  const languageRules = (config.languageRules || []).map((rule) => ({
    language: rule.language,
    patterns: rule.patterns.map(([source, weight]) => [new RegExp(source, rule.flags), weight]),
  }));

  function languageForFilename(name) {
    const base = name.toLowerCase().split("/").pop();
    const dot = base.lastIndexOf(".");
    const extension = dot > 0 ? base.slice(dot) : "";
    return config.filenameLanguages[base] || config.extensionLanguages[extension] || null;
  }

  function detectLanguage(code) {
    let best = null;
    let bestScore = 0;
    for (const rule of languageRules) {
      const score = rule.patterns.reduce((sum, [pattern, weight]) => sum + (pattern.test(code) ? weight : 0), 0);
      if (score > bestScore) {
        best = rule.language;
        bestScore = score;
      }
    }
    return bestScore >= config.minLanguageScore ? best : null;
  }

  function updateDetectedLanguage() {
    const label = $("detected-language");
    label.hidden = !CODE_PAGE || !textInput.value.trim();
    if (label.hidden) return;
    const language = detectLanguage(textInput.value);
    label.replaceChildren();
    if (language) {
      const [before, after] = t("detectedLanguage").split("{language}");
      const name = document.createElement("strong");
      name.textContent = language;
      label.append(before, name, after || "");
    } else {
      label.textContent = t("unknownLanguage");
    }
  }

  // ── Page setup ──────────────────────────────────────────
  function fileAllowed(name) {
    if (CODE_PAGE) return languageForFilename(name) !== null;
    const dot = name.lastIndexOf(".");
    return DOCUMENT_EXTENSIONS.includes(dot > 0 ? name.slice(dot).toLowerCase() : "");
  }

  fileInput.multiple = CODE_PAGE;
  fileInput.accept = (CODE_PAGE ? Object.keys(config.extensionLanguages) : DOCUMENT_EXTENSIONS).join(",");
  textInput.classList.toggle("code", CODE_PAGE);

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

  // A document replaces the chosen file; code files are added to the list.
  function addFiles(list) {
    hideError();
    const incoming = Array.from(list || []);
    if (!incoming.length) return;
    const files = CODE_PAGE ? selectedFiles.slice() : [];
    for (const file of CODE_PAGE ? incoming : incoming.slice(0, 1)) {
      if (!fileAllowed(file.name)) return showError("errType", { name: file.name });
      if (!files.some((f) => f.name === file.name && f.size === file.size)) files.push(file);
    }
    if (files.length > config.maxCodeFiles) return showError("errTooManyFiles", { files: config.maxCodeFiles });
    const total = files.reduce((sum, file) => sum + file.size, 0);
    if (total > config.maxUploadMb * 1024 * 1024) return showError("errSize", { mb: config.maxUploadMb });
    selectedFiles = files;
    renderFiles();
  }

  function renderFiles() {
    const chips = selectedFiles.map((file, index) => {
      const chip = chipTemplate.content.firstElementChild.cloneNode(true);
      chip.querySelector(".name").textContent = file.name;
      chip.querySelector(".size").textContent = formatSize(file.size);
      if (CODE_PAGE) {
        const badge = chip.querySelector(".lang-badge");
        badge.textContent = languageForFilename(file.name);
        badge.hidden = false;
      }
      const remove = chip.querySelector(".remove");
      remove.setAttribute("aria-label", t("removeFile") + ": " + file.name);
      remove.addEventListener("click", () => {
        selectedFiles.splice(index, 1);
        renderFiles();
      });
      return chip;
    });
    fileList.replaceChildren(...chips);
    fileList.hidden = !chips.length;
    fileInput.value = "";
  }

  fileInput.addEventListener("change", () => addFiles(fileInput.files));

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
    if (event.dataTransfer) addFiles(event.dataTransfer.files);
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
  textInput.addEventListener("input", () => {
    updateCharCount();
    updateDetectedLanguage();
  });

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
      if (!selectedFiles.length) return showError("errNoFile");
      for (const file of selectedFiles) data.append("file", file, file.name);
    } else {
      // Code keeps its indentation and has no minimum length; documents need the full text.
      const text = CODE_PAGE ? textInput.value : textInput.value.trim();
      if (CODE_PAGE ? !text.trim() : text.length < 50) {
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

  function codeBlock(kind, code) {
    const figure = document.createElement("figure");
    figure.className = "code-block " + kind;
    const caption = document.createElement("figcaption");
    const label = document.createElement("span");
    label.textContent = t(kind === "added" ? "suggested" : "current");
    caption.append(label);
    if (kind === "added" && navigator.clipboard) {
      const copy = document.createElement("button");
      copy.type = "button";
      copy.className = "copy";
      copy.textContent = t("copy");
      copy.addEventListener("click", async () => {
        try {
          await navigator.clipboard.writeText(code);
          copy.textContent = t("copied");
          setTimeout(() => { copy.textContent = t("copy"); }, 1500);
        } catch (error) { /* clipboard not allowed */ }
      });
      caption.append(copy);
    }
    const pre = document.createElement("pre");
    const codeElement = document.createElement("code");
    codeElement.textContent = code;
    pre.append(codeElement);
    figure.append(caption, pre);
    return figure;
  }

  function renderSuggestions(items) {
    const list = $("suggestion-list");
    list.replaceChildren();
    for (const item of items || []) {
      const li = document.createElement("li");
      li.className = "suggestion";
      const head = document.createElement("p");
      head.className = "suggestion-head";
      const where = [item.file, item.line ? t("line", { n: item.line }) : ""].filter(Boolean).join(" · ");
      if (where) {
        const location = document.createElement("code");
        location.textContent = where;
        head.append(location, " ");
      }
      head.append(item.issue);
      li.append(head);
      if (item.original) li.append(codeBlock("removed", item.original));
      li.append(codeBlock("added", item.replacement));
      list.append(li);
    }
    $("suggestions").hidden = !list.children.length;
  }

  // ── Production readiness and security (code page) ──────
  const TONES = {
    ready: "good", needs_work: "warn", not_ready: "bad",
    none: "good", low: "warn", medium: "warn", high: "bad", critical: "bad",
  };
  const ICONS = { good: "✓", warn: "!", bad: "✕" };

  function setBadge(element, value, label) {
    const tone = TONES[value] || "warn";
    element.dataset.tone = tone;
    const icon = document.createElement("span");
    icon.setAttribute("aria-hidden", "true");
    icon.textContent = ICONS[tone];
    element.replaceChildren(icon, label);
  }

  function renderVerdicts(production, security) {
    $("verdicts").hidden = !production && !security;
    $("production").hidden = !production;
    if (production) {
      setBadge($("production-badge"), production.verdict, t("verdict_" + production.verdict));
      $("production-reason").textContent = production.reason || "";
    }
    $("security").hidden = !security;
    const issues = security ? security.issues || [] : [];
    if (security) {
      setBadge($("security-badge"), security.risk, t("risk_" + security.risk));
      $("security-count").textContent = issues.length === 0 ? t("noIssues")
        : issues.length === 1 ? t("issueCountOne") : t("issueCount", { count: issues.length });
    }

    const list = $("security-list");
    list.replaceChildren(...issues.map((issue) => {
      const li = document.createElement("li");
      li.className = "security-issue";
      const head = document.createElement("div");
      head.className = "issue-head";
      const severity = document.createElement("span");
      severity.className = "severity";
      severity.dataset.tone = TONES[issue.severity];
      severity.textContent = t("risk_" + issue.severity);
      const title = document.createElement("strong");
      title.textContent = issue.title;
      head.append(severity, title);
      const where = [issue.file, issue.line ? t("line", { n: issue.line }) : ""].filter(Boolean).join(" · ");
      if (where) {
        const location = document.createElement("code");
        location.className = "where";
        location.textContent = where;
        head.append(location);
      }
      if (issue.cwe) {
        const link = document.createElement("a");
        link.href = "https://cwe.mitre.org/data/definitions/" + issue.cwe.slice(4) + ".html";
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        link.textContent = issue.cwe;
        head.append(link);
      }
      li.append(head);
      if (issue.detail) {
        const detail = document.createElement("p");
        detail.textContent = issue.detail;
        li.append(detail);
      }
      return li;
    }));
    $("security-issues").hidden = !issues.length;
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
    if (data.languages && data.languages.length) parts.push(data.languages.join(", "));
    $("result-meta").textContent = parts.join(" · ");

    $("summary").textContent = data.summary || "—";
    fillList("strengths", data.strengths);
    fillList("weaknesses", data.weaknesses);
    renderVerdicts(data.production, data.security);
    renderSuggestions(data.suggestions);
  }

  $("again").addEventListener("click", () => {
    result.hidden = true;
    lastResult = null;
    form.scrollIntoView({ behavior: "smooth", block: "start" });
  });

  setLanguage(pickInitialLanguage());
})();
