const STORAGE = {
  jobId: "docxPrintOrder.jobId",
  mode: "docxPrintOrder.mode",
  sequence: "docxPrintOrder.sequence",
  skipRecent: "docxPrintOrder.skipRecent",
  stampUi: "docxPrintOrder.stampUi",
};

function syncEmbeddedTheme() {
  if (!document.body.classList.contains("embedded")) return;
  const applyTheme = () => {
    try {
      const parentTheme = window.parent?.document?.documentElement?.dataset?.theme;
      document.body.classList.toggle("theme-dark", parentTheme === "dark");
    } catch {
      document.body.classList.toggle("theme-dark", window.matchMedia("(prefers-color-scheme: dark)").matches);
    }
  };
  applyTheme();
  try {
    const parentRoot = window.parent.document.documentElement;
    new MutationObserver(applyTheme).observe(parentRoot, { attributes: true, attributeFilter: ["data-theme"] });
  } catch {
    window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", applyTheme);
  }
}

syncEmbeddedTheme();

const STEPS = ["documents", "order", "check", "result"];

const state = {
  jobId: null,
  mode: null,
  excelFile: null,
  canBuild: false,
  currentStep: "documents",
  pollTimer: null,
  lastValidation: null,
  lastJob: null,
  registrationPreview: null,
  activeFilter: "all",
  resultLimit: 160,
  expandedGroups: new Set(),
  connectionLost: false,
  stampingHydratedForJob: null,
  stampPreviewUrl: null,
  registrationExternalLoadedFileKey: null,
  registrationExpandedPartyNo: null,
  pendingFiles: [],
  pendingSkipped: 0,
  pendingFolderNames: new Set(),
  txtFiles: [],
  sequenceBeforeSort: null,
  sequenceInternalUpdate: false,
  stampSourceMode: "auto_sequence",
};

const els = {
  taskStatus: document.querySelector("#taskStatus"),
  newTaskButton: document.querySelector("#newTaskButton"),
  menuButton: document.querySelector("#menuButton"),
  taskMenu: document.querySelector("#taskMenu"),
  menuReportLink: document.querySelector("#menuReportLink"),
  menuDetailsButton: document.querySelector("#menuDetailsButton"),
  menuPrintButton: document.querySelector("#menuPrintButton"),
  menuDeleteButton: document.querySelector("#menuDeleteButton"),
  downloadBar: document.querySelector("#downloadBar"),
  downloadTitle: document.querySelector("#downloadTitle"),
  downloadActions: document.querySelector("#downloadActions"),
  stepItems: [...document.querySelectorAll(".step-item")],
  documentsScreen: document.querySelector("#documentsScreen"),
  orderScreen: document.querySelector("#orderScreen"),
  checkScreen: document.querySelector("#checkScreen"),
  resultScreen: document.querySelector("#resultScreen"),
  dropZone: document.querySelector("#dropZone"),
  fileInput: document.querySelector("#fileInput"),
  folderInput: document.querySelector("#folderInput"),
  selectFilesButton: document.querySelector("#selectFilesButton"),
  selectFolderButton: document.querySelector("#selectFolderButton"),
  pendingQueue: document.querySelector("#pendingQueue"),
  pendingQueueTitle: document.querySelector("#pendingQueueTitle"),
  pendingQueueSummary: document.querySelector("#pendingQueueSummary"),
  pendingQueueHint: document.querySelector("#pendingQueueHint"),
  clearQueueButton: document.querySelector("#clearQueueButton"),
  uploadQueueButton: document.querySelector("#uploadQueueButton"),
  uploadSummary: document.querySelector("#uploadSummary"),
  uploadStatus: document.querySelector("#uploadStatus"),
  acceptedCount: document.querySelector("#acceptedCount"),
  excelCountText: document.querySelector("#excelCountText"),
  showFilesButton: document.querySelector("#showFilesButton"),
  modeSelector: document.querySelector("#modeSelector"),
  textModeButton: document.querySelector("#textModeButton"),
  excelModeButton: document.querySelector("#excelModeButton"),
  registrationModeButton: document.querySelector("#registrationModeButton"),
  selectedModeBar: document.querySelector("#selectedModeBar"),
  selectedModeText: document.querySelector("#selectedModeText"),
  changeModeButton: document.querySelector("#changeModeButton"),
  textModePanel: document.querySelector("#textModePanel"),
  excelModePanel: document.querySelector("#excelModePanel"),
  registrationModePanel: document.querySelector("#registrationModePanel"),
  registrationPermissionNote: document.querySelector("#registrationPermissionNote"),
  registrationStartPartyInput: document.querySelector("#registrationStartPartyInput"),
  registrationYearInput: document.querySelector("#registrationYearInput"),
  registrationPerPartyInput: document.querySelector("#registrationPerPartyInput"),
  registrationStartRcsmeInput: document.querySelector("#registrationStartRcsmeInput"),
  registrationIntakeDateInput: document.querySelector("#registrationIntakeDateInput"),
  registrationDecisionDateInput: document.querySelector("#registrationDecisionDateInput"),
  registrationInvestigatorInput: document.querySelector("#registrationInvestigatorInput"),
  registrationIncomingInput: document.querySelector("#registrationIncomingInput"),
  registrationBoxInput: document.querySelector("#registrationBoxInput"),
  registrationExternalInput: document.querySelector("#registrationExternalInput"),
  registrationExternalTxtInput: document.querySelector("#registrationExternalTxtInput"),
  registrationExternalXlsxInput: document.querySelector("#registrationExternalXlsxInput"),
  clearRegistrationExternalButton: document.querySelector("#clearRegistrationExternalButton"),
  registrationExternalCount: document.querySelector("#registrationExternalCount"),
  registrationExternalWarnings: document.querySelector("#registrationExternalWarnings"),
  registrationSummary: document.querySelector("#registrationSummary"),
  previewRegistrationButton: document.querySelector("#previewRegistrationButton"),
  applyRegistrationButton: document.querySelector("#applyRegistrationButton"),
  registrationPreview: document.querySelector("#registrationPreview"),
  txtInput: document.querySelector("#txtInput"),
  txtFilesSummary: document.querySelector("#txtFilesSummary"),
  sequenceInput: document.querySelector("#sequenceInput"),
  sequenceCount: document.querySelector("#sequenceCount"),
  sortSequenceButton: document.querySelector("#sortSequenceButton"),
  undoSortButton: document.querySelector("#undoSortButton"),
  clearSequenceButton: document.querySelector("#clearSequenceButton"),
  validateButton: document.querySelector("#validateButton"),
  orderValidationNotice: document.querySelector("#orderValidationNotice"),
  orderValidationTitle: document.querySelector("#orderValidationTitle"),
  orderValidationText: document.querySelector("#orderValidationText"),
  viewOrderValidationButton: document.querySelector("#viewOrderValidationButton"),
  xlsxInput: document.querySelector("#xlsxInput"),
  validateExcelButton: document.querySelector("#validateExcelButton"),
  excelFileState: document.querySelector("#excelFileState"),
  excelModeHint: document.querySelector("#excelModeHint"),
  stampPanel: document.querySelector("#stampPanel"),
  stampEnabledInput: document.querySelector("#stampEnabledInput"),
  stampControls: document.querySelector("#stampControls"),
  stampPanelTitle: document.querySelector("#stampPanelTitle"),
  stampPanelSubtitle: document.querySelector("#stampPanelSubtitle"),
  stampControlsTitle: document.querySelector("#stampControlsTitle"),
  stampControlsSubtitle: document.querySelector("#stampControlsSubtitle"),
  stampSourceActions: document.querySelector("#stampSourceActions"),
  stampAutoBlock: document.querySelector("#stampAutoBlock"),
  stampManualBlock: document.querySelector("#stampManualBlock"),
  stampStartNumberInput: document.querySelector("#stampStartNumberInput"),
  showGeneratedNumbersButton: document.querySelector("#showGeneratedNumbersButton"),
  useManualStampButton: document.querySelector("#useManualStampButton"),
  useAutoStampButton: document.querySelector("#useAutoStampButton"),
  stampGeneratedPreview: document.querySelector("#stampGeneratedPreview"),
  stampTxtInput: document.querySelector("#stampTxtInput"),
  stampXlsxInput: document.querySelector("#stampXlsxInput"),
  clearStampButton: document.querySelector("#clearStampButton"),
  stampTextBlock: document.querySelector("#stampTextBlock"),
  stampTextInput: document.querySelector("#stampTextInput"),
  stampExcelGroups: document.querySelector("#stampExcelGroups"),
  stampRejectDuplicatesRow: document.querySelector("#stampRejectDuplicatesRow"),
  stampRejectDuplicatesInput: document.querySelector("#stampRejectDuplicatesInput"),
  stampAllowSkipRow: document.querySelector("#stampAllowSkipRow"),
  stampAllowSkipInput: document.querySelector("#stampAllowSkipInput"),
  stampCornerInput: document.querySelector("#stampCornerInput"),
  stampMarginXInput: document.querySelector("#stampMarginXInput"),
  stampMarginYInput: document.querySelector("#stampMarginYInput"),
  stampFontSizeInput: document.querySelector("#stampFontSizeInput"),
  stampBoldInput: document.querySelector("#stampBoldInput"),
  stampBackgroundInput: document.querySelector("#stampBackgroundInput"),
  stampBorderInput: document.querySelector("#stampBorderInput"),
  stampRotationInput: document.querySelector("#stampRotationInput"),
  stampSummary: document.querySelector("#stampSummary"),
  stampValidationActions: document.querySelector("#stampValidationActions"),
  applyStampingButton: document.querySelector("#applyStampingButton"),
  stampPreviewButton: document.querySelector("#stampPreviewButton"),
  stampWarnings: document.querySelector("#stampWarnings"),
  stampPreviewFigure: document.querySelector("#stampPreviewFigure"),
  stampPreviewImage: document.querySelector("#stampPreviewImage"),
  stampPreviewCaption: document.querySelector("#stampPreviewCaption"),
  checkSubtitle: document.querySelector("#checkSubtitle"),
  validationSummary: document.querySelector("#validationSummary"),
  warningGroups: document.querySelector("#warningGroups"),
  resultTools: document.querySelector("#resultTools"),
  filterButtons: document.querySelector("#filterButtons"),
  resultSearch: document.querySelector("#resultSearch"),
  resultsArea: document.querySelector("#resultsArea"),
  buildButton: document.querySelector("#buildButton"),
  progressPanel: document.querySelector("#progressPanel"),
  resultPanel: document.querySelector("#resultPanel"),
  progressBar: document.querySelector("#progressBar"),
  progressText: document.querySelector("#progressText"),
  progressDetails: document.querySelector("#progressDetails"),
  pipelineCheck: document.querySelector("#pipelineCheck"),
  pipelineConvert: document.querySelector("#pipelineConvert"),
  pipelineMerge: document.querySelector("#pipelineMerge"),
  pipelineDownload: document.querySelector("#pipelineDownload"),
  resultTitle: document.querySelector("#resultTitle"),
  resultMetrics: document.querySelector("#resultMetrics"),
  resultBlock: document.querySelector("#resultBlock"),
  partsList: document.querySelector("#partsList"),
  toast: document.querySelector("#toast"),
  confirmDialog: document.querySelector("#confirmDialog"),
  confirmTitle: document.querySelector("#confirmTitle"),
  confirmText: document.querySelector("#confirmText"),
  confirmOkButton: document.querySelector("#confirmOkButton"),
  confirmAltButton: document.querySelector("#confirmAltButton"),
  confirmCancelButton: document.querySelector("#confirmCancelButton"),
  detailsDialog: document.querySelector("#detailsDialog"),
  taskDetails: document.querySelector("#taskDetails"),
  filesDialog: document.querySelector("#filesDialog"),
  filesList: document.querySelector("#filesList"),
};

function persistState() {
  if (state.jobId) localStorage.setItem(STORAGE.jobId, state.jobId);
  else localStorage.removeItem(STORAGE.jobId);
  if (state.mode) localStorage.setItem(STORAGE.mode, state.mode);
  else localStorage.removeItem(STORAGE.mode);
  localStorage.setItem(STORAGE.sequence, els.sequenceInput.value);
}

function setJobId(jobId) {
  state.jobId = jobId;
  persistState();
}

function forgetLocalTask() {
  state.jobId = null;
  state.mode = null;
  state.excelFile = null;
  state.canBuild = false;
  state.lastValidation = null;
  state.lastJob = null;
  state.registrationPreview = null;
  state.registrationExternalLoadedFileKey = null;
  state.registrationExpandedPartyNo = null;
  state.pendingFiles = [];
  state.pendingSkipped = 0;
  state.pendingFolderNames.clear();
  state.txtFiles = [];
  state.sequenceBeforeSort = null;
  state.activeFilter = "all";
  state.resultLimit = 160;
  state.expandedGroups.clear();
  state.stampingHydratedForJob = null;
  state.stampSourceMode = "auto_sequence";
  els.stampEnabledInput.checked = true;
  els.stampBorderInput.checked = true;
  els.stampStartNumberInput.value = "";
  els.stampTextInput.value = "";
  els.orderValidationNotice.hidden = true;
  els.sequenceInput.value = "";
  els.registrationExternalInput.value = "";
  els.registrationExternalWarnings.innerHTML = "";
  localStorage.removeItem(STORAGE.jobId);
  localStorage.removeItem(STORAGE.mode);
  localStorage.removeItem(STORAGE.sequence);
  stopPolling();
  renderPendingQueue();
  renderTxtFilesSummary();
}

function setStep(step) {
  if (!STEPS.includes(step)) return;
  state.currentStep = step;
  els.documentsScreen.hidden = step !== "documents";
  els.orderScreen.hidden = step !== "order";
  els.checkScreen.hidden = step !== "check";
  els.resultScreen.hidden = step !== "result";
  updateStepper();
  updateHeader();
}

function updateStepper() {
  const activeIndex = STEPS.indexOf(state.currentStep);
  const stats = state.lastValidation ? getValidationStats(state.lastValidation) : null;
  els.stepItems.forEach((item) => {
    const step = item.dataset.step;
    const index = STEPS.indexOf(step);
    item.className = "step-item";
    item.disabled = !isStepAvailable(step);
    item.removeAttribute("aria-current");
    if (index < activeIndex || isStepDone(step)) item.classList.add("done");
    if (step === state.currentStep) {
      item.classList.add("current");
      item.setAttribute("aria-current", "step");
    }
    if (step === "check" && stats?.errors) item.classList.add("error");
    if (step === "check" && !stats?.errors && stats?.warnings) item.classList.add("warning");
  });
}

function isStepAvailable(step) {
  if (step === "documents") return true;
  if (step === "order") return Boolean(state.jobId);
  if (step === "check") return Boolean(state.lastValidation);
  if (step === "result") return ["converting", "ready", "failed"].includes(state.lastJob?.status);
  return false;
}

function isStepDone(step) {
  if (step === "documents") return Boolean(state.jobId);
  if (step === "order") return Boolean(state.lastValidation);
  if (step === "check") return state.lastValidation?.can_build || state.lastJob?.status === "ready";
  if (step === "result") return state.lastJob?.status === "ready";
  return false;
}

function updateHeader() {
  const status = state.lastJob?.status;
  if (!state.jobId) {
    setStatus("Нет задания", "neutral");
  } else if (status === "ready") {
    setStatus("✓ Готово", "good");
  } else if (status === "converting") {
    setStatus("● Сборка", "info");
  } else if (status === "failed") {
    setStatus("✕ Ошибка", "bad");
  } else if (state.lastValidation) {
    setStatus(state.lastValidation.can_build ? "✓ Проверено" : "✕ Есть ошибки", state.lastValidation.can_build ? "good" : "bad");
  } else {
    setStatus("Документы загружены", "neutral");
  }
  const reportReady = Boolean(state.jobId && state.lastJob?.report_csv);
  els.menuReportLink.href = reportReady ? `/api/print/jobs/${state.jobId}/download/report.csv` : "#";
  els.menuReportLink.setAttribute("aria-disabled", reportReady ? "false" : "true");
  els.downloadBar.hidden = state.lastJob?.status !== "ready" || state.currentStep === "result";
}

function setStatus(text, type) {
  els.taskStatus.textContent = text;
  els.taskStatus.className = `status-pill ${type}`;
}

function showToast(text) {
  els.toast.textContent = text;
  els.toast.hidden = false;
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => {
    els.toast.hidden = true;
  }, 4200);
}

function addInlineNotice(text, type = "info") {
  const node = document.createElement("div");
  node.className = `issue-card ${type === "error" ? "error" : type === "warning" ? "warning" : ""}`;
  node.textContent = text;
  els.resultsArea.prepend(node);
}

async function readJson(response) {
  const text = await response.text();
  return text ? JSON.parse(text) : {};
}

function queuedFile(record) {
  return record?.file || record;
}

function queuedRelativePath(record) {
  const file = queuedFile(record);
  return String(record?.relativePath || file?.webkitRelativePath || file?.name || "")
    .replaceAll("\\", "/")
    .replace(/^\/+/, "");
}

function uploadCounts(records) {
  const incoming = [...records];
  return {
    excelFiles: incoming.filter((record) => queuedFile(record).name.toLowerCase().endsWith(".xlsx")),
    documentFiles: incoming.filter((record) => !queuedFile(record).name.toLowerCase().endsWith(".xlsx")),
  };
}

function queuedFileKey(record) {
  const file = queuedFile(record);
  const path = queuedRelativePath(record) || file.name;
  return `${path}:${file.size}:${file.lastModified}`;
}

function queueRecords(records, { folderSelection = false } = {}) {
  const existing = new Set(state.pendingFiles.map(queuedFileKey));
  let added = 0;
  let skipped = 0;
  records.forEach((record) => {
    const file = queuedFile(record);
    const relativePath = queuedRelativePath(record);
    const name = file.name.toLowerCase();
    const temporary = file.name.startsWith("~$");
    const fromFolder = folderSelection || record?.source === "folder" || relativePath.includes("/");
    const supported = fromFolder ? name.endsWith(".docx") : /\.(docx|zip|xlsx)$/.test(name);
    if (temporary) return;
    if (!supported) {
      skipped += 1;
      return;
    }
    const normalized = { file, relativePath, source: fromFolder ? "folder" : "file" };
    const key = queuedFileKey(normalized);
    if (existing.has(key)) return;
    existing.add(key);
    state.pendingFiles.push(normalized);
    added += 1;
    if (normalized.source === "folder" && relativePath.includes("/")) {
      state.pendingFolderNames.add(relativePath.split("/")[0]);
    }
  });
  state.pendingSkipped += skipped;
  const excelRecord = state.pendingFiles.find((record) => queuedFile(record).name.toLowerCase().endsWith(".xlsx"));
  state.excelFile = excelRecord ? queuedFile(excelRecord) : state.excelFile;
  renderPendingQueue();
  renderModePanels();
  if (added || skipped) {
    const parts = [`Добавлено: ${added}`];
    if (skipped) parts.push(`пропущено: ${skipped}`);
    showToast(parts.join(" · "));
  }
}

function readDirectoryBatch(reader) {
  return new Promise((resolve, reject) => reader.readEntries(resolve, reject));
}

async function droppedEntryRecords(entry) {
  if (entry.isFile) {
    const file = await new Promise((resolve, reject) => entry.file(resolve, reject));
    return [{ file, relativePath: String(entry.fullPath || file.name).replace(/^\/+/, ""), source: "file" }];
  }
  if (!entry.isDirectory) return [];
  const reader = entry.createReader();
  const children = [];
  while (true) {
    const batch = await readDirectoryBatch(reader);
    if (!batch.length) break;
    children.push(...batch);
  }
  const nested = await Promise.all(children.map((child) => droppedEntryRecords(child)));
  return nested.flat().map((record) => ({ ...record, source: "folder" }));
}

async function droppedRecords(dataTransfer) {
  const entries = [...(dataTransfer.items || [])]
    .map((item) => item.webkitGetAsEntry?.())
    .filter(Boolean);
  if (!entries.length) return [...dataTransfer.files].map((file) => ({ file, relativePath: file.name, source: "file" }));
  const groups = await Promise.all(entries.map((entry) => droppedEntryRecords(entry)));
  return groups.flat();
}

function renderPendingQueue() {
  const records = state.pendingFiles;
  els.pendingQueue.hidden = records.length === 0;
  if (!records.length) return;
  const docx = records.filter((record) => queuedFile(record).name.toLowerCase().endsWith(".docx")).length;
  const zip = records.filter((record) => queuedFile(record).name.toLowerCase().endsWith(".zip")).length;
  const xlsx = records.filter((record) => queuedFile(record).name.toLowerCase().endsWith(".xlsx")).length;
  const bytes = records.reduce((sum, record) => sum + queuedFile(record).size, 0);
  const folderCount = state.pendingFolderNames.size;
  const individualCount = records.filter((record) => record.source === "file").length;
  els.pendingQueueTitle.textContent = "Подготовлено к загрузке:";
  els.pendingQueueSummary.innerHTML = `
    <span>Документов: <strong>${docx}</strong></span>
    <span>Папок: <strong>${folderCount}</strong></span>
    <span>Отдельных файлов: <strong>${individualCount}</strong></span>
    ${zip ? `<span>ZIP-архивов: <strong>${zip}</strong></span>` : ""}
    ${xlsx ? `<span>Excel-файлов: <strong>${xlsx}</strong></span>` : ""}
    <span>Размер: <strong>${formatBytes(bytes)}</strong></span>
  `;
  els.pendingQueueHint.textContent = state.pendingSkipped
    ? `${state.pendingSkipped} ${plural(state.pendingSkipped, "неподдерживаемый файл пропущен", "неподдерживаемых файла пропущено", "неподдерживаемых файлов пропущено")}`
    : "Можно добавить ещё файлы или папки перед загрузкой.";
  const error = pendingQueueLimitError();
  els.uploadQueueButton.disabled = Boolean(error) || docx + zip === 0;
  els.uploadQueueButton.textContent = "Загрузить документы";
  if (error) els.pendingQueueHint.textContent = error;
}

function pendingQueueLimitError() {
  const maxFiles = Number(document.body.dataset.maxFiles || 2000);
  const maxUploadBytes = Number(document.body.dataset.maxUploadMb || 500) * 1024 * 1024;
  const maxSingleBytes = Number(document.body.dataset.maxSingleFileMb || 50) * 1024 * 1024;
  const docxCount = state.pendingFiles.filter((record) => queuedFile(record).name.toLowerCase().endsWith(".docx")).length;
  if (docxCount > maxFiles) return `Слишком много DOCX: ${docxCount}. Лимит: ${maxFiles}.`;
  const oversized = state.pendingFiles.find((record) => queuedFile(record).size > maxSingleBytes);
  if (oversized) return `Файл ${queuedFile(oversized).name} превышает лимит ${document.body.dataset.maxSingleFileMb || 50} МБ.`;
  const total = state.pendingFiles.reduce((sum, record) => sum + queuedFile(record).size, 0);
  if (total > maxUploadBytes) return `Общий размер ${formatBytes(total)} превышает лимит ${document.body.dataset.maxUploadMb || 500} МБ.`;
  return "";
}

async function uploadFiles(records) {
  const { excelFiles, documentFiles } = uploadCounts(records);
  if (excelFiles.length) {
    state.excelFile = queuedFile(excelFiles[0]);
    renderModePanels();
    if (state.mode === "registration" && state.jobId) {
      await loadSelectedExcelAsRegistrationExternalNumbers();
    }
  }
  if (!documentFiles.length) {
    if (state.excelFile && state.jobId) {
      showToast("Excel выбран");
      if (!state.mode) selectMode("excel");
      return;
    }
    showToast("Excel выбран. Теперь загрузите DOCX или ZIP с документами.");
    return;
  }

  setStatus("Загружаем…", "info");
  const formData = new FormData();
  [...documentFiles, ...excelFiles.slice(0, 1)].forEach((record) => {
    const file = queuedFile(record);
    formData.append("files", file, queuedRelativePath(record) || file.name);
  });
  try {
    const response = await fetch("/api/print/jobs", { method: "POST", body: formData });
    const data = await readJson(response);
    if (!response.ok) throw new Error(data.detail || "Не удалось загрузить документы");
    setJobId(data.id);
    localStorage.removeItem(STORAGE.skipRecent);
    state.lastJob = {
      id: data.id,
      status: data.status,
      documents: data.documents,
      validation: null,
      build: null,
      registration_external_numbers: data.registration_external_excel?.all_labels || [],
    };
    if (data.registration_external_excel?.all_labels?.length) {
      applyRegistrationExternalNumbersFromExcel(state.excelFile, data.registration_external_excel);
      state.registrationExternalLoadedFileKey = fileKey(state.excelFile);
    }
    state.pendingFiles = [];
    state.pendingSkipped = 0;
    state.pendingFolderNames.clear();
    renderPendingQueue();
    renderUploadSummary(state.lastJob);
    showToast(`Загружено ${data.accepted_documents} ${plural(data.accepted_documents, "DOCX", "DOCX", "DOCX")}`);
    setStep("order");
    if (state.mode === "registration" && state.excelFile) {
      await loadSelectedExcelAsRegistrationExternalNumbers();
    }
  } catch (error) {
    setStatus("Ошибка загрузки", "bad");
    showErrorInOrder(error.message);
  } finally {
    renderModePanels();
    updateHeader();
  }
}

function fileKey(file) {
  return file ? `${file.name}:${file.size}:${file.lastModified}` : "";
}

function showErrorInOrder(message) {
  setStep(state.jobId ? "order" : "documents");
  els.validationSummary.innerHTML = "";
  els.resultsArea.innerHTML = "";
  const node = createIssueCard("Ошибка", message, "Проверьте файл и попробуйте загрузить ещё раз.", "error");
  if (state.currentStep === "documents") {
    els.uploadSummary.hidden = false;
    els.uploadStatus.textContent = "Ошибка загрузки";
    els.uploadStatus.className = "status-pill bad";
    els.acceptedCount.textContent = message;
    els.excelCountText.hidden = false;
    els.excelCountText.textContent = "Загрузка не завершена";
  } else {
    els.resultsArea.append(node);
  }
}

function renderUploadSummary(job) {
  const docs = job?.documents || [];
  if (!state.jobId && !docs.length) {
    els.uploadSummary.hidden = true;
    return;
  }
  els.uploadSummary.hidden = false;
  els.uploadStatus.textContent = job?.status === "ready" ? "✓ Задание восстановлено" : "✓ Документы загружены";
  els.uploadStatus.className = "status-pill good";
  els.acceptedCount.textContent = `Загружено ${docs.length} ${plural(docs.length, "DOCX", "DOCX", "DOCX")}`;
  els.excelCountText.hidden = !state.excelFile;
  els.excelCountText.textContent = state.excelFile ? `Выбран Excel-файл: ${state.excelFile.name}` : "";
}

function selectMode(mode) {
  state.mode = mode;
  state.activeFilter = "all";
  persistState();
  renderModePanels();
  if (mode === "registration") {
    loadSelectedExcelAsRegistrationExternalNumbers();
  }
}

function renderModePanels() {
  const hasMode = Boolean(state.mode);
  const canEdit = document.body.dataset.canEdit === "1";
  els.modeSelector.hidden = hasMode;
  els.selectedModeBar.hidden = !hasMode;
  els.textModePanel.hidden = state.mode !== "text";
  els.excelModePanel.hidden = state.mode !== "excel";
  els.registrationModePanel.hidden = state.mode !== "registration";
  els.stampPanel.hidden = !hasMode;
  els.textModeButton.classList.toggle("selected", state.mode === "text");
  els.excelModeButton.classList.toggle("selected", state.mode === "excel");
  els.registrationModeButton.classList.toggle("selected", state.mode === "registration");
  els.registrationPermissionNote.hidden = canEdit;
  els.previewRegistrationButton.disabled = !canEdit || !state.jobId;
  els.applyRegistrationButton.disabled = !canEdit || !state.registrationPreview || Boolean(state.registrationPreview.conflicts?.length);
  if (state.mode === "text") {
    els.selectedModeText.textContent = "Выбран способ: Один список. Вставьте номера или загрузите TXT, затем нажмите «Проверить порядок».";
  } else if (state.mode === "excel") {
    els.selectedModeText.textContent = "Выбран способ: Таблица Excel. Загрузите Excel-файл и нажмите «Проверить Excel».";
  } else if (state.mode === "registration") {
    els.selectedModeText.textContent = "Выбран способ: Новые партии. Заполните данные и проверьте будущие партии.";
  }
  updateSequenceCount();
  renderExcelState();
  updateRegistrationExternalCount();
  renderRegistrationPreview();
  renderStampingPanel();
}

function hydrateStampingUi(validation) {
  const config = validation?.stamping?.config;
  if (!config || state.stampingHydratedForJob === `${state.jobId}:${validation.mode}`) return;
  state.stampingHydratedForJob = `${state.jobId}:${validation.mode}`;
  els.stampEnabledInput.checked = Boolean(config.enabled);
  state.stampSourceMode = config.source === "manual" ? "manual" : "auto_sequence";
  els.stampStartNumberInput.value = config.start_number || "";
  els.stampTextInput.value = config.text || "";
  els.stampRejectDuplicatesInput.checked = Boolean(config.reject_duplicates);
  els.stampAllowSkipInput.checked = Boolean(config.allow_skip);
  const style = config.style || {};
  els.stampCornerInput.value = style.corner || "top_left";
  els.stampRotationInput.value = style.rotation || "none";
  els.stampMarginXInput.value = style.margin_x_mm ?? 10;
  els.stampMarginYInput.value = style.margin_y_mm ?? 8;
  els.stampFontSizeInput.value = style.font_size ?? 12;
  els.stampBoldInput.checked = Boolean(style.bold);
  els.stampBackgroundInput.checked = Boolean(style.white_background);
  els.stampBorderInput.checked = style.border !== false;
}

function renderStampingPanel() {
  const isRegistration = state.mode === "registration";
  if (isRegistration) {
    els.stampEnabledInput.checked = true;
  }
  els.stampEnabledInput.disabled = isRegistration;
  els.stampPanelTitle.textContent = isRegistration ? "Нанести № постановления на документы" : "Нанести номера на документы";
  els.stampPanelSubtitle.textContent = isRegistration
    ? "Номера формируются из создаваемой регистрации, здесь настраивается только внешний вид нанесения."
    : "Укажите начальный номер, остальные будут рассчитаны по порядку документов.";
  els.stampControlsTitle.textContent = isRegistration ? "Настройки нанесения" : "Нумерация документов";
  els.stampControlsSubtitle.textContent = isRegistration
    ? "Выберите угол, поворот, отступы, размер шрифта, фон и рамку для системного номера."
    : "Количество и диапазон будут рассчитаны после проверки порядка.";
  const enabled = isRegistration || els.stampEnabledInput.checked;
  els.stampControls.hidden = !enabled;
  const manualSource = state.stampSourceMode === "manual";
  els.stampAutoBlock.hidden = isRegistration || manualSource;
  els.stampManualBlock.hidden = isRegistration || !manualSource;
  els.stampSourceActions.hidden = isRegistration;
  els.stampTextBlock.hidden = isRegistration || state.mode === "excel";
  els.stampRejectDuplicatesRow.hidden = isRegistration;
  els.stampAllowSkipRow.hidden = isRegistration;
  els.stampValidationActions.hidden = isRegistration;
  const showExcelGroups = manualSource && state.mode === "excel" && Boolean(state.lastValidation?.groups?.length);
  els.stampExcelGroups.hidden = !showExcelGroups;
  if (showExcelGroups) renderStampGroupInputs();
  saveStampUiSettings();
  updateStampSummary();
}

function renderStampGroupInputs() {
  const groups = state.lastValidation?.groups || [];
  const existing = new Map(
    [...els.stampExcelGroups.querySelectorAll("[data-stamp-group-text]")].map((node) => [
      node.dataset.groupId,
      node.value,
    ]),
  );
  els.stampExcelGroups.innerHTML = "";
  groups.forEach((group) => {
    const groupId = group.id || group.column || group.title;
    const groupConfig = state.lastValidation?.stamping?.config?.groups?.[groupId] || {};
    const text = existing.get(groupId) ?? groupConfig.text ?? "";
    const card = document.createElement("div");
    card.className = "stamp-group-card";
    card.innerHTML = `
      <strong>${escapeHtml(group.title)}</strong>
      <span>${group.validation.total} ${plural(group.validation.total, "документ", "документа", "документов")} · столбец ${escapeHtml(group.column)}</span>
      <label class="field-label" for="stampGroup_${escapeAttr(groupId)}">Метки для этого PDF</label>
      <textarea id="stampGroup_${escapeAttr(groupId)}" rows="5" spellcheck="false" data-stamp-group-text data-group-id="${escapeAttr(groupId)}" placeholder="6528-2026&#10;6529-2026">${escapeHtml(text)}</textarea>
    `;
    els.stampExcelGroups.append(card);
  });
  els.stampExcelGroups.querySelectorAll("[data-stamp-group-text]").forEach((node) => {
    node.addEventListener("input", () => {
      markStampAssignmentDirty();
      updateStampSummary();
    });
  });
}

function renderExcelState() {
  if (state.lastValidation?.mode === "excel") {
    const groups = state.lastValidation.groups || [];
    const documents = groups.reduce((sum, group) => sum + (group.validation?.entries?.length || 0), 0);
    els.excelFileState.textContent = `Файл проверен: ${state.excelFile?.name || "Excel"}. Документов: ${documents}. Будет создано PDF: ${groups.length}.`;
    els.excelModeHint.textContent = els.stampEnabledInput.checked
      ? `Excel проверен: ${groups.length} ${plural(groups.length, "PDF", "PDF", "PDF")}. Теперь загрузите номера для нанесения и нажмите «Проверить метки».`
      : `Excel проверен. Будет создано PDF: ${groups.length}.`;
  } else if (state.excelFile) {
    els.excelFileState.textContent = `Выбран файл: ${state.excelFile.name}`;
    els.excelModeHint.textContent = "Нажмите «Проверить Excel», чтобы найти столбцы и документы.";
  } else {
    els.excelFileState.textContent = "Excel-файл ещё не выбран.";
    els.excelModeHint.textContent = "Выберите XLSX-файл.";
  }
  els.validateExcelButton.disabled = !state.jobId || !state.excelFile;
}

function registrationPayload() {
  const startParty = els.registrationStartPartyInput.value.trim();
  const caseYear = Number(els.registrationYearInput.value || new Date().getFullYear());
  const perParty = Number(els.registrationPerPartyInput.value || 100);
  if (!startParty) throw new Error("Укажите стартовую партию");
  if (!Number.isFinite(caseYear)) throw new Error("Укажите год");
  if (!Number.isFinite(perParty) || perParty < 1) throw new Error("Укажите количество DOCX в партии");
  const stampStyle = collectStampingConfig().style;
  return {
    start_party_no: startParty,
    case_year: caseYear,
    documents_per_party: perParty,
    start_rcsme_reg_no: els.registrationStartRcsmeInput.value.trim() || null,
    external_military_numbers: registrationExternalNumbers(),
    intake_date: els.registrationIntakeDateInput.value || null,
    decision_date: els.registrationDecisionDateInput.value || null,
    investigator: els.registrationInvestigatorInput.value.trim() || null,
    incoming_no: els.registrationIncomingInput.value.trim() || null,
    box_no: els.registrationBoxInput.value.trim() || null,
    stamp_field: "decree_no",
    stamping: { style: stampStyle },
  };
}

function registrationExternalSourceLabel(source) {
  if (source === "list") return "Список";
  if (source === "filename") return "Имя DOCX";
  return "Не задано";
}

function registrationExternalNumbers() {
  return els.registrationExternalInput.value
    .replace(/\ufeff/g, "")
    .replace(/[–—−]/g, "-")
    .split(/[\s,;]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function updateRegistrationExternalCount() {
  const numbers = registrationExternalNumbers();
  const docs = state.lastJob?.documents?.length || 0;
  const diff = docs - numbers.length;
  const duplicates = numbers.length - new Set(numbers.map((item) => item.toLocaleLowerCase("ru"))).size;
  const parts = numbers.length
    ? [`${numbers.length} ${plural(numbers.length, "номер", "номера", "номеров")}`]
    : ["0 номеров"];
  if (numbers.length && docs) {
    if (diff === 0) parts.push("количество совпадает");
    else if (diff > 0) parts.push(`не хватает ${diff}`);
    else parts.push(`лишних ${Math.abs(diff)}`);
  }
  if (duplicates) parts.push(`повторов ${duplicates}`);
  els.registrationExternalCount.textContent = parts.join(" · ");
}

function resetRegistrationPreview() {
  state.registrationPreview = null;
  state.registrationExpandedPartyNo = null;
  renderRegistrationPreview();
  renderModePanels();
}

async function previewAutoRegistration() {
  if (!state.jobId) return;
  setStatus("Считаем партии…", "info");
  els.previewRegistrationButton.disabled = true;
  try {
    const response = await fetch(`/api/print/jobs/${state.jobId}/registration/preview`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(registrationPayload()),
    });
    const data = await readJson(response);
    if (!response.ok) throw new Error(data.detail || "Не удалось построить предпросмотр партий");
    state.registrationPreview = data;
    els.registrationStartRcsmeInput.placeholder = data.suggested_start_rcsme_reg_no || "автоматически";
    renderRegistrationPreview();
    showToast(`Предпросмотр: ${data.party_count} ${plural(data.party_count, "партия", "партии", "партий")}`);
  } catch (error) {
    state.registrationPreview = null;
    els.registrationPreview.innerHTML = "";
    els.registrationSummary.textContent = error.message;
    showToast(error.message);
  } finally {
    updateHeader();
    renderModePanels();
  }
}

async function applyAutoRegistration() {
  if (!state.jobId) return;
  const preview = state.registrationPreview;
  const message = preview
    ? `Будет создано объектов: ${preview.total_objects}; партий: ${preview.parties_to_create}. Продолжить?`
    : "Создать партии и подготовить печать?";
  const ok = await askConfirm({
    title: "Создать партии и объекты?",
    text: message,
    okText: "Создать",
  });
  if (!ok) return;
  setStatus("Создаём объекты…", "info");
  els.applyRegistrationButton.disabled = true;
  try {
    const response = await fetch(`/api/print/jobs/${state.jobId}/registration/apply`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(registrationPayload()),
    });
    const data = await readJson(response);
    if (!response.ok) throw new Error(data.detail || "Не удалось создать партии");
    state.mode = "registration";
    state.registrationPreview = data.registration;
    state.lastValidation = data.validation;
    state.lastJob = { ...(state.lastJob || {}), status: "validated", validation: data.validation, build: null, registration: data.registration };
    state.canBuild = data.validation.can_build;
    state.activeFilter = "all";
    state.resultLimit = 160;
    persistState();
    renderValidation(data.validation);
    showToast(`Создано объектов: ${data.registration.objects_created}`);
    setStep("check");
  } catch (error) {
    showToast(error.message);
    renderRegistrationPreview();
  } finally {
    updateHeader();
    renderModePanels();
  }
}

function renderRegistrationPreview() {
  if (state.mode !== "registration") return;
  const preview = state.registrationPreview || state.lastJob?.registration;
  if (!preview) {
    const docs = state.lastJob?.documents?.length || 0;
    els.registrationSummary.textContent = docs
      ? `Загружено ${docs} DOCX. Укажите стартовую партию и выполните предпросмотр.`
      : "Сначала загрузите DOCX.";
    els.registrationPreview.innerHTML = "";
    return;
  }
  const conflictCount = preview.conflicts?.length || 0;
  els.registrationSummary.textContent = conflictCount
    ? `Есть конфликты: ${conflictCount}`
    : `Партий: ${preview.party_count} · объектов: ${preview.total_objects} · старт № РЦСМЭ: ${preview.requested_start_rcsme_reg_no}`;
  const warningHtml = [
    ...(preview.conflicts || []).slice(0, 5).map((item) => `<article class="issue-card error"><strong>Конфликт</strong><p>${escapeHtml(item)}</p></article>`),
    ...(preview.warnings || []).slice(0, 5).map((item) => `<article class="issue-card warning"><strong>Внимание</strong><p>${escapeHtml(item)}</p></article>`),
  ].join("");
  const rows = (preview.parties || []).flatMap((party) => {
    const expanded = state.registrationExpandedPartyNo === String(party.party_no);
    const summary = `
      <tr class="registration-party-summary">
        <td><button class="row-action secondary" type="button" data-registration-party="${escapeAttr(party.party_no)}">${expanded ? "▾" : "▸"} № ${escapeHtml(party.party_no)}</button></td>
        <td>${escapeHtml(String(party.object_count))} DOCX</td>
        <td>${escapeHtml(party.first_rcsme_reg_no || "—")} → ${escapeHtml(party.last_rcsme_reg_no || "—")}</td>
        <td>${escapeHtml(party.first_decree_no || "—")} → ${escapeHtml(party.last_decree_no || "—")}</td>
        <td>${escapeHtml(party.first_external_military_no || "—")} → ${escapeHtml(party.last_external_military_no || "—")}</td>
        <td><span class="badge ${party.status === "конфликт" ? "bad" : party.existing_party_id ? "warn" : "good"}">${escapeHtml(party.status)}</span></td>
      </tr>`;
    if (!expanded) return [summary];
    const details = (party.sample_rows || []).map((row) => `
      <tr class="registration-object-row">
        <td>↳ ${escapeHtml(row.index)}</td>
        <td class="truncate" title="${escapeAttr(row.document_name)}">${escapeHtml(row.document_name)}</td>
        <td>${escapeHtml(row.rcsme_reg_no)}</td>
        <td>${escapeHtml(row.decree_no)}</td>
        <td>${escapeHtml(row.external_military_no || "—")}</td>
        <td>${registrationExternalSourceLabel(row.external_military_no_source)}</td>
      </tr>
    `);
    if ((party.sample_rows || []).length < party.object_count) {
      details.push(`<tr class="registration-object-row"><td colspan="6"><small>Показаны первые ${party.sample_rows?.length || 0} из ${party.object_count} объектов.</small></td></tr>`);
    }
    return [summary, ...details];
  }).join("");
  const sourceText = preview.external_military_no_source === "list"
    ? `Из списка: ${preview.external_military_no_count || 0}`
    : "Не задано";
  els.registrationPreview.innerHTML = `
    <div class="metric-grid">
      <div class="metric"><span>Партий</span><strong>${preview.party_count}</strong></div>
      <div class="metric"><span>Объектов</span><strong>${preview.total_objects}</strong></div>
      <div class="metric"><span>Будет создано партий</span><strong>${preview.parties_to_create}</strong></div>
      <div class="metric"><span>Старт № РЦСМЭ</span><strong>${escapeHtml(preview.requested_start_rcsme_reg_no)}</strong></div>
      <div class="metric"><span>№ в в/ч №522</span><strong>${escapeHtml(sourceText)}</strong></div>
    </div>
    ${preview.previous_party_no ? `<div class="selected-mode"><span>После партии ${escapeHtml(preview.previous_party_no)}: ${escapeHtml(preview.previous_last_rcsme_reg_no || "—")}</span></div>` : ""}
    ${warningHtml}
    <div class="table-wrap registration-preview-table">
      <table>
        <thead><tr><th>Партия / №</th><th>DOCX</th><th>№ рег РЦСМЭ</th><th>№ постановления / метка</th><th>№ в в/ч №522</th><th>Статус / источник</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
  `;
  els.registrationPreview.querySelectorAll("[data-registration-party]").forEach((button) => {
    button.addEventListener("click", () => {
      const partyNo = button.dataset.registrationParty;
      state.registrationExpandedPartyNo = state.registrationExpandedPartyNo === partyNo ? null : partyNo;
      renderRegistrationPreview();
    });
  });
}

function getSequenceInfo() {
  const rows = els.sequenceInput.value
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
  const unique = new Set(rows.map((line) => line.toLocaleLowerCase("ru")));
  return { rows, total: rows.length, unique: unique.size, hasDuplicates: unique.size < rows.length };
}

function labelLines(text) {
  return text
    .replace(/\ufeff/g, "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
}

function normalizeTxtBoundary(text) {
  return String(text || "").replace(/\r\n?/g, "\n").replace(/\n+$/g, "");
}

function joinTxtContents(contents) {
  return contents.map(normalizeTxtBoundary).join("\n");
}

function renderTxtFilesSummary() {
  els.txtFilesSummary.hidden = state.txtFiles.length === 0;
  if (!state.txtFiles.length) {
    els.txtFilesSummary.innerHTML = "";
    return;
  }
  const total = state.txtFiles.reduce((sum, item) => sum + item.count, 0);
  const visible = state.txtFiles.slice(0, 5);
  els.txtFilesSummary.innerHTML = `
    <strong>Загружено списков: ${state.txtFiles.length} · номеров: ${total}</strong>
    <div class="file-summary-list">
      ${visible.map((item) => `<span><span title="${escapeAttr(item.name)}">${escapeHtml(item.name)}</span><b>${item.count}</b></span>`).join("")}
      ${state.txtFiles.length > visible.length ? `<small>+ ещё ${state.txtFiles.length - visible.length} файлов</small>` : ""}
    </div>
  `;
}

async function loadSequenceTxtFiles(files) {
  const selected = [...files];
  if (!selected.length) return;
  const loaded = await Promise.all(selected.map(async (file) => {
    const text = await file.text();
    return { name: file.name, text, count: labelLines(text).length };
  }));
  const combined = joinTxtContents(loaded.map((item) => item.text));
  let choice = "replace";
  if (els.sequenceInput.value.trim()) {
    choice = await askListMergeChoice();
    if (choice === "cancel") return;
  }
  invalidateTextValidation();
  if (choice === "append") {
    els.sequenceInput.value = joinTxtContents([els.sequenceInput.value, combined]);
    state.txtFiles.push(...loaded);
  } else {
    els.sequenceInput.value = combined;
    state.txtFiles = loaded;
  }
  state.sequenceBeforeSort = null;
  els.undoSortButton.hidden = true;
  updateSequenceCount();
  renderTxtFilesSummary();
  showToast(`Загружено списков: ${loaded.length} · номеров: ${loaded.reduce((sum, item) => sum + item.count, 0)}`);
}

const SORT_CONFUSABLES = {
  "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "х": "x",
  "у": "y", "к": "k", "м": "m", "т": "t", "н": "h", "в": "b",
};

function naturalSortParts(value) {
  const normalized = String(value)
    .normalize("NFC")
    .toLocaleLowerCase("ru")
    .replace(/[аеорсхукмтнв]/g, (char) => SORT_CONFUSABLES[char] || char);
  return (normalized.match(/\d+|\D+/g) || []).map((part) => (/^\d+$/.test(part)
    ? { number: true, value: part.replace(/^0+(?=\d)/, "") }
    : { number: false, value: part }));
}

function compareNaturalValues(left, right) {
  const a = naturalSortParts(left);
  const b = naturalSortParts(right);
  for (let index = 0; index < Math.max(a.length, b.length); index += 1) {
    if (!a[index]) return -1;
    if (!b[index]) return 1;
    if (a[index].number && b[index].number) {
      if (a[index].value.length !== b[index].value.length) return a[index].value.length - b[index].value.length;
      const result = a[index].value.localeCompare(b[index].value);
      if (result) return result;
      continue;
    }
    if (a[index].number !== b[index].number) return a[index].number ? -1 : 1;
    const result = a[index].value.localeCompare(b[index].value, "ru", { sensitivity: "base" });
    if (result) return result;
  }
  return 0;
}

function sortSequenceNaturally() {
  const rows = labelLines(els.sequenceInput.value);
  if (!rows.length) {
    showToast("Список номеров пуст");
    return;
  }
  const sorted = rows
    .map((value, index) => ({ value, index }))
    .sort((left, right) => compareNaturalValues(left.value, right.value) || left.index - right.index)
    .map((item) => item.value);
  const nextValue = sorted.join("\n");
  const alreadySorted = nextValue === els.sequenceInput.value.trim();
  if (alreadySorted) {
    showToast("Список уже отсортирован");
    return;
  }
  invalidateTextValidation();
  state.sequenceBeforeSort = els.sequenceInput.value;
  els.sequenceInput.value = nextValue;
  els.undoSortButton.hidden = false;
  updateSequenceCount();
  showToast(`${sorted.length} ${plural(sorted.length, "номер отсортирован", "номера отсортированы", "номеров отсортированы")} по возрастанию`);
}

function undoSequenceSort() {
  if (state.sequenceBeforeSort === null) return;
  invalidateTextValidation();
  els.sequenceInput.value = state.sequenceBeforeSort;
  state.sequenceBeforeSort = null;
  els.undoSortButton.hidden = true;
  updateSequenceCount();
  showToast("Исходный порядок восстановлен");
}

function collectStampingConfig() {
  const groups = {};
  els.stampExcelGroups.querySelectorAll("[data-stamp-group-text]").forEach((node) => {
    groups[node.dataset.groupId] = { text: node.value };
  });
  return {
    enabled: state.mode === "registration" || els.stampEnabledInput.checked,
    source: state.mode === "registration" ? "registration" : state.stampSourceMode,
    start_number: state.mode === "registration" ? "" : els.stampStartNumberInput.value.trim(),
    text: state.mode === "registration" ? "" : els.stampTextInput.value,
    groups: state.mode === "registration" ? {} : groups,
    reject_duplicates: state.mode === "registration" ? false : els.stampRejectDuplicatesInput.checked,
    allow_skip: state.mode === "registration" ? false : els.stampAllowSkipInput.checked,
    style: {
      corner: els.stampCornerInput.value,
      rotation: els.stampRotationInput.value,
      margin_x_mm: Number(els.stampMarginXInput.value || 10),
      margin_y_mm: Number(els.stampMarginYInput.value || 8),
      font_size: Number(els.stampFontSizeInput.value || 12),
      bold: els.stampBoldInput.checked,
      white_background: els.stampBackgroundInput.checked,
      border: els.stampBorderInput.checked,
    },
  };
}

function collectExcelValidationStampingConfig() {
  const config = collectStampingConfig();
  if (config.enabled && config.source === "auto_sequence" && !state.lastValidation?.groups?.length) {
    return { ...config, enabled: false };
  }
  const hasGroupLabels = Object.values(config.groups).some((group) => labelLines(group.text || "").length > 0);
  if (config.enabled && config.source === "manual" && !hasGroupLabels) {
    return { ...config, enabled: false };
  }
  return config;
}

function collectTextValidationStampingConfig() {
  const config = collectStampingConfig();
  return config.enabled ? { ...config, enabled: false } : config;
}

function generatedStampLabels(count) {
  const match = els.stampStartNumberInput.value.trim().match(/^(\d+)-(\d{4})$/);
  if (!match) return null;
  const width = match[1].length;
  const start = Number(match[1]);
  return Array.from({ length: Math.max(0, count) }, (_, index) => (
    `${String(start + index).padStart(width, "0")}-${match[2]}`
  ));
}

function setStampSourceMode(source) {
  state.stampSourceMode = source === "manual" ? "manual" : "auto_sequence";
  els.stampGeneratedPreview.hidden = true;
  els.showGeneratedNumbersButton.textContent = "Показать список";
  markStampAssignmentDirty();
  renderStampingPanel();
}

function markStampAssignmentDirty() {
  if (!state.lastValidation || state.mode === "registration") return;
  state.canBuild = false;
  els.buildButton.disabled = true;
  els.orderValidationNotice.hidden = false;
  els.orderValidationNotice.classList.remove("has-errors");
  els.orderValidationTitle.textContent = "Нумерация изменена";
  els.orderValidationText.textContent = "Присвоенные номера будут пересчитаны после повторной проверки.";
}

function updateStampSummary() {
  if (state.mode === "registration") {
    els.stampSummary.textContent = "Будет нанесён № постановления из предпросмотра регистрации";
    els.applyStampingButton.disabled = true;
    els.stampPreviewButton.disabled = true;
    els.stampWarnings.innerHTML = "";
    if (els.stampBackgroundInput.checked) {
      els.stampWarnings.append(createIssueCard("Белый фон может закрыть часть исходного документа", "", "", "warning"));
    }
    saveStampUiSettings();
    return;
  }
  const enabled = els.stampEnabledInput.checked;
  if (!enabled) {
    els.stampSummary.textContent = "Нанесение выключено";
    els.applyStampingButton.disabled = true;
    els.stampPreviewButton.disabled = true;
    els.stampWarnings.innerHTML = "";
    return;
  }
  const documents = stampDocumentCount();
  const labels = stampLabelCount();
  if (state.stampSourceMode === "auto_sequence") {
    const sequence = generatedStampLabels(documents);
    const hasValidatedOrder = Boolean(state.lastValidation);
    if (!els.stampStartNumberInput.value.trim()) {
      els.stampSummary.textContent = hasValidatedOrder
        ? `Документов: ${documents} · Укажите начальный номер`
        : "Сначала проверьте порядок документов и укажите начальный номер";
    } else if (!sequence) {
      els.stampSummary.textContent = "Укажите начальный номер в формате 7658-2026.";
    } else if (!hasValidatedOrder) {
      els.stampSummary.textContent = "Сначала проверьте порядок документов. После проверки номера будут рассчитаны автоматически.";
    } else {
      els.stampSummary.textContent = `Будет создано: ${sequence.length} · Первый: ${sequence[0] || "—"} · Последний: ${sequence.at(-1) || "—"}`;
    }
    els.applyStampingButton.disabled = !hasValidatedOrder || !sequence;
    els.stampPreviewButton.disabled = !canShowStampPreview(documents, labels);
    els.showGeneratedNumbersButton.disabled = !hasValidatedOrder || !sequence;
    if (!els.stampGeneratedPreview.hidden) {
      els.stampGeneratedPreview.textContent = sequence?.join("\n") || "";
    }
    els.stampWarnings.innerHTML = "";
    if (els.stampBackgroundInput.checked) {
      els.stampWarnings.append(createIssueCard("Белый фон может закрыть часть исходного документа", "", "", "warning"));
    }
    saveStampUiSettings();
    return;
  }
  const diff = documents - labels;
  const duplicates = stampDuplicateCount();
  const skipCount = stampSkipCount();
  const parts = [`Документов: ${documents}`, `Меток: ${labels}`];
  if (diff === 0) parts.push("Соответствие: готово");
  else if (diff > 0) parts.push(`Не хватает: ${diff}`);
  else parts.push(`Лишних: ${Math.abs(diff)}`);
  if (skipCount) parts.push(`SKIP: ${skipCount}`);
  if (duplicates) parts.push(`Повторов: ${duplicates}`);
  els.stampSummary.textContent = parts.join(" · ");
  els.applyStampingButton.disabled = !state.lastValidation;
  els.stampPreviewButton.disabled = !canShowStampPreview(documents, labels);
  els.stampWarnings.innerHTML = "";
  if (els.stampBackgroundInput.checked) {
    els.stampWarnings.append(createIssueCard("Белый фон может закрыть часть исходного документа", "", "", "warning"));
  }
  if (duplicates && !els.stampRejectDuplicatesInput.checked) {
    els.stampWarnings.append(createIssueCard(`Найдены повторяющиеся метки: ${duplicates}`, "Повторы разрешены, но будут нанесены как указано.", "", "warning"));
  }
  saveStampUiSettings();
}

function canShowStampPreview(documents, labels) {
  if (!state.jobId || !els.stampEnabledInput.checked || documents === 0 || labels === 0) return false;
  if (state.mode === "excel") return Boolean(state.lastValidation);
  return state.mode === "text";
}

function stampDocumentCount() {
  if (state.mode === "excel" && state.lastValidation?.groups?.length) {
    return state.lastValidation.groups.reduce((sum, group) => sum + (group.validation?.total || 0), 0);
  }
  if (state.lastValidation) return getValidationStats(state.lastValidation).total;
  return getSequenceInfo().total;
}

function stampLabelCount() {
  if (state.stampSourceMode === "auto_sequence") {
    return generatedStampLabels(stampDocumentCount())?.length || 0;
  }
  if (state.mode === "excel" && state.lastValidation?.groups?.length) {
    return [...els.stampExcelGroups.querySelectorAll("[data-stamp-group-text]")].reduce(
      (sum, node) => sum + labelLines(node.value).length,
      0,
    );
  }
  return labelLines(els.stampTextInput.value).length;
}

function stampDuplicateCount() {
  const labels = stampAllLabels().filter((label) => !(els.stampAllowSkipInput.checked && label.toUpperCase() === "SKIP"));
  const counts = new Map();
  labels.forEach((label) => counts.set(label, (counts.get(label) || 0) + 1));
  return [...counts.values()].reduce((sum, count) => sum + Math.max(0, count - 1), 0);
}

function stampSkipCount() {
  if (!els.stampAllowSkipInput.checked) return 0;
  return stampAllLabels().filter((label) => label.toUpperCase() === "SKIP").length;
}

function stampAllLabels() {
  if (state.stampSourceMode === "auto_sequence") {
    return generatedStampLabels(stampDocumentCount()) || [];
  }
  if (state.mode === "excel" && state.lastValidation?.groups?.length) {
    return [...els.stampExcelGroups.querySelectorAll("[data-stamp-group-text]")].flatMap((node) => labelLines(node.value));
  }
  return labelLines(els.stampTextInput.value);
}

function saveStampUiSettings() {
  const safe = {
    reject_duplicates: els.stampRejectDuplicatesInput.checked,
    allow_skip: els.stampAllowSkipInput.checked,
    style: collectStampingConfig().style,
  };
  localStorage.setItem(STORAGE.stampUi, JSON.stringify(safe));
}

function restoreStampUiSettings() {
  try {
    const safe = JSON.parse(localStorage.getItem(STORAGE.stampUi) || "{}");
    els.stampEnabledInput.checked = true;
    state.stampSourceMode = "auto_sequence";
    els.stampRejectDuplicatesInput.checked = Boolean(safe.reject_duplicates);
    els.stampAllowSkipInput.checked = Boolean(safe.allow_skip);
    const style = safe.style || {};
    els.stampCornerInput.value = style.corner || "top_left";
    els.stampRotationInput.value = style.rotation || "none";
    els.stampMarginXInput.value = style.margin_x_mm ?? 10;
    els.stampMarginYInput.value = style.margin_y_mm ?? 8;
    els.stampFontSizeInput.value = style.font_size ?? 12;
    els.stampBoldInput.checked = Boolean(style.bold);
    els.stampBackgroundInput.checked = Boolean(style.white_background);
    els.stampBorderInput.checked = true;
  } catch {
    // UI settings are optional.
  }
}

function updateSequenceCount() {
  const info = getSequenceInfo();
  els.sequenceCount.textContent = `${info.total} ${plural(info.total, "номер", "номера", "номеров")}`;
  els.validateButton.disabled = !state.jobId || state.mode !== "text" || info.total === 0;
  localStorage.setItem(STORAGE.sequence, els.sequenceInput.value);
  updateStampSummary();
}

function invalidateTextValidation() {
  if (state.mode !== "text" || !state.lastValidation) return;
  const assignedNumbersInvalidated = els.stampEnabledInput.checked;
  state.lastValidation = null;
  state.canBuild = false;
  state.lastJob = { ...(state.lastJob || {}), status: "uploaded", validation: null, build: null };
  els.orderValidationNotice.hidden = !assignedNumbersInvalidated;
  if (assignedNumbersInvalidated) {
    els.orderValidationNotice.classList.remove("has-errors");
    els.orderValidationTitle.textContent = "Порядок изменён";
    els.orderValidationText.textContent = "Присвоенные номера будут пересчитаны после повторной проверки порядка.";
  }
  persistState();
  updateStepper();
}

function renderOrderValidationNotice(validation) {
  const stats = getValidationStats(validation);
  els.orderValidationNotice.hidden = false;
  els.orderValidationNotice.classList.toggle("has-errors", stats.errors > 0);
  els.orderValidationTitle.textContent = stats.errors ? "Порядок проверен, есть ошибки" : "✓ Порядок проверен";
  els.orderValidationText.textContent = stats.errors
    ? `Найдено документов: ${stats.matched} из ${stats.total} · ошибок: ${stats.errors}. Исправьте порядок или откройте подробности.`
    : `Найдено документов: ${stats.matched} из ${stats.total} · ошибок: 0. Теперь укажите начальный номер и нажмите «Проверить номера».`;
}

async function validateTextJob() {
  if (!state.jobId) return;
  const stampingEnabled = els.stampEnabledInput.checked;
  setStatus("Проверяем…", "info");
  els.validateButton.disabled = true;
  try {
    const response = await fetch(`/api/print/jobs/${state.jobId}/validate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sequence: els.sequenceInput.value, stamping: collectTextValidationStampingConfig() }),
    });
    const data = await readJson(response);
    if (!response.ok) throw new Error(data.detail || "Не удалось проверить порядок");
    state.mode = "text";
    state.lastValidation = data;
    state.lastJob = { ...(state.lastJob || {}), status: "validated", validation: data, build: null };
    state.canBuild = data.can_build;
    state.activeFilter = getValidationStats(data).errors ? "errors" : "all";
    state.resultLimit = 160;
    persistState();
    renderValidation(data);
    if (stampingEnabled) {
      renderOrderValidationNotice(data);
      setStep("order");
    } else {
      els.orderValidationNotice.hidden = true;
      setStep("check");
    }
  } catch (error) {
    renderValidationError(error.message);
    if (stampingEnabled) {
      els.orderValidationNotice.hidden = false;
      els.orderValidationNotice.classList.add("has-errors");
      els.orderValidationTitle.textContent = "Не удалось проверить порядок";
      els.orderValidationText.textContent = error.message;
      setStep("order");
    } else {
      setStep("check");
    }
  } finally {
    updateHeader();
    updateSequenceCount();
  }
}

async function validateExcelJob() {
  if (!state.jobId || !state.excelFile) return;
  const stampingEnabled = els.stampEnabledInput.checked;
  setStatus("Проверяем Excel-файл…", "info");
  els.validateExcelButton.disabled = true;
  const formData = new FormData();
  formData.append("file", state.excelFile);
  formData.append("stamping_json", JSON.stringify(collectExcelValidationStampingConfig()));
  try {
    const response = await fetch(`/api/print/jobs/${state.jobId}/validate/excel`, {
      method: "POST",
      body: formData,
    });
    const data = await readJson(response);
    if (!response.ok) throw new Error(data.detail || "Не удалось проверить Excel");
    state.mode = "excel";
    state.lastValidation = data;
    state.lastJob = { ...(state.lastJob || {}), status: "validated", validation: data, build: null };
    state.canBuild = data.can_build;
    state.activeFilter = getValidationStats(data).errors ? "errors" : "all";
    state.resultLimit = 160;
    persistState();
    renderModePanels();
    renderValidation(data);
    setStep(stampingEnabled ? "order" : "check");
  } catch (error) {
    renderValidationError(error.message);
    setStep("check");
  } finally {
    renderModePanels();
    updateHeader();
  }
}

async function applyStampingToCurrentValidation({ goToCheck = true, toastText = "Метки проверены" } = {}) {
  if (!state.jobId || !state.lastValidation) return;
  setStatus("Проверяем метки…", "info");
  try {
    const response = await fetch(`/api/print/jobs/${state.jobId}/stamping`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ stamping: collectStampingConfig() }),
    });
    const data = await readJson(response);
    if (!response.ok) throw new Error(data.detail || "Не удалось применить метки");
    state.lastValidation = data;
    state.lastJob = { ...(state.lastJob || {}), status: "validated", validation: data, build: null };
    state.canBuild = data.can_build;
    state.activeFilter = getValidationStats(data).errors ? "errors" : "all";
    renderValidation(data);
    if (data.can_build) {
      els.orderValidationNotice.hidden = true;
      showToast(toastText);
      if (goToCheck) setStep("check");
    } else {
      renderOrderValidationNotice(data);
      showToast("В метках есть ошибки");
      setStep("order");
    }
    return true;
  } catch (error) {
    showToast(error.message);
    return false;
  } finally {
    updateHeader();
    updateStampSummary();
  }
}

async function readPreviewBlob(response) {
  if (!response.ok) {
    const contentType = response.headers.get("content-type") || "";
    if (contentType.includes("application/json")) {
      const data = await readJson(response);
      throw new Error(data.detail || "Не удалось построить пример");
    }
    const text = await response.text();
    throw new Error(text || "Не удалось построить пример");
  }
  return response.blob();
}

function setStampPreviewImage(blob, caption) {
  if (state.stampPreviewUrl) URL.revokeObjectURL(state.stampPreviewUrl);
  state.stampPreviewUrl = URL.createObjectURL(blob);
  els.stampPreviewImage.src = state.stampPreviewUrl;
  els.stampPreviewCaption.textContent = caption;
  els.stampPreviewFigure.hidden = false;
}

async function showStampPreview() {
  if (!state.jobId) return;
  setStatus("Готовим пример…", "info");
  try {
    if (state.mode === "text") {
      const response = await fetch(`/api/print/jobs/${state.jobId}/stamping/preview`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sequence: els.sequenceInput.value, stamping: collectStampingConfig() }),
      });
      const blob = await readPreviewBlob(response);
      const number = getSequenceInfo().rows[0] || "первый документ";
      const label = stampAllLabels()[0] || "";
      setStampPreviewImage(blob, label ? `Документ: ${number} · Метка: ${label}` : "Пример нанесения метки");
      showToast("Пример обновлён");
      return;
    }
    if (!state.lastValidation) {
      showToast("Для Excel сначала выполните проверку таблицы");
      return;
    }
    const ok = await applyStampingToCurrentValidation({
      goToCheck: false,
      toastText: "Метки обновлены",
    });
    if (!ok) return;
    const response = await fetch(`/api/print/jobs/${state.jobId}/stamping/preview?t=${Date.now()}`);
    const blob = await readPreviewBlob(response);
    const first = flatEntries(state.lastValidation).find((entry) => entry.doc_id && entry.stamp_label);
    setStampPreviewImage(
      blob,
      first ? `Документ: ${first.number} · Метка: ${first.stamp_label}` : "Пример нанесения метки",
    );
    showToast("Пример обновлён");
  } catch (error) {
    showToast(error.message);
  } finally {
    updateHeader();
  }
}

function renderValidationError(message) {
  state.canBuild = false;
  els.validationSummary.innerHTML = "";
  els.warningGroups.innerHTML = "";
  els.resultTools.hidden = true;
  els.resultsArea.innerHTML = "";
  els.resultsArea.append(createIssueCard("Ошибка проверки", message, "Проверьте данные и запустите проверку ещё раз.", "error"));
  els.buildButton.hidden = true;
}

function renderValidation(validation) {
  const stats = getValidationStats(validation);
  els.checkSubtitle.textContent = stats.errors
    ? "Есть ошибки, сборку запускать нельзя."
    : "Можно запускать сборку.";

  const title = stats.errors
    ? "Сначала исправьте ошибки"
    : "Всё готово к сборке";
  els.validationSummary.innerHTML = `
    <div class="summary-title">
      <h3>${escapeHtml(title)}</h3>
      <span class="status-pill ${stats.errors ? "bad" : "good"}">${stats.errors ? "Сборка недоступна" : "Можно собирать"}</span>
    </div>
    <div class="metric-grid">
      <div class="metric"><span>Документов</span><strong>${stats.matched}</strong></div>
      <div class="metric"><span>PDF будет создано</span><strong>${stats.pdfCount}</strong></div>
      <div class="metric"><span>Присвоено номеров</span><strong>${stats.assignedCount}</strong></div>
      <div class="metric"><span>Диапазон</span><strong>${escapeHtml(stats.assignedCount ? `${stats.assignedFirst} — ${stats.assignedLast}` : "—")}</strong></div>
      <div class="metric"><span>Ошибок</span><strong>${stats.errors}</strong></div>
      <div class="metric"><span>Предупреждений</span><strong>${stats.warnings}</strong></div>
    </div>
  `;

  renderWarningGroups(validation, stats);
  renderFilterButtons(stats);
  renderResults(validation);
  els.buildButton.hidden = false;
  els.buildButton.disabled = !validation.can_build;
  els.buildButton.textContent = ["excel", "registration"].includes(validation.mode)
    ? `Собрать ${stats.pdfCount} ${plural(stats.pdfCount, "PDF", "PDF", "PDF")}`
    : "Собрать PDF";
  updateStepper();
  renderStampingPanel();
}

function getValidationStats(validation) {
  const entries = flatEntries(validation);
  const entryErrors = entries.filter((entry) => entry.blocking).length;
  const errors = Math.max(entryErrors, validation.blocking_errors?.length || 0);
  const warningEntries = entries.filter((entry) => entry.warnings?.length).length;
  const matched = entries.filter((entry) => entry.doc_id).length;
  const topWarnings = validation.warnings?.length || 0;
  const stampSummary = validation.stamping?.summary || {};
  const assigned = entries
    .map((entry) => entry.assigned_number || entry.stamp_label || "")
    .filter(Boolean);
  return {
    entries,
    total: entries.length,
    matched,
    errors,
    warningEntries,
    warnings: warningEntries + topWarnings,
    ready: entries.length - errors,
    pdfCount: validation.mode === "excel"
      ? validation.total_groups || validation.groups?.length || 0
      : validation.mode === "registration"
        ? validation.registration?.party_count || 0
        : 1,
    stampLabels: stampSummary.labels || 0,
    stampApplied: stampSummary.applied || 0,
    stampSkipped: stampSummary.skipped || 0,
    assignedCount: assigned.length,
    assignedFirst: assigned[0] || "",
    assignedLast: assigned.at(-1) || "",
  };
}

function renderWarningGroups(validation, stats) {
  els.warningGroups.innerHTML = "";
  if (!stats.warnings) return;
  const groups = new Map();
  flatEntries(validation).forEach((entry) => {
    (entry.warnings || []).forEach((warning) => {
      const key = warning.split(":")[0].slice(0, 110);
      groups.set(key, (groups.get(key) || 0) + 1);
    });
  });
  (validation.warnings || []).forEach((warning) => {
    const key = warning.replace(/\d+$/, "").trim() || warning;
    groups.set(key, (groups.get(key) || 0) + 1);
  });
  const details = document.createElement("details");
  details.className = "warning-details";
  const firstWarning = [...groups.keys()][0] || "Проверьте дополнительные замечания.";
  details.innerHTML = `
    <summary>
      <span><strong>Есть предупреждения: ${stats.warnings}</strong><small>Например: ${escapeHtml(firstWarning)}</small></span>
      <span class="details-action">Показать подробности</span>
    </summary>
    <div class="warning-detail-list"></div>
  `;
  const list = details.querySelector(".warning-detail-list");
  [...groups.entries()].forEach(([message, count]) => {
    list.append(createIssueCard(`${count} — ${message}`, "", "", "warning"));
  });
  els.warningGroups.append(details);
}

function createIssueCard(title, text, action, type) {
  const node = document.createElement("article");
  node.className = `issue-card ${type === "error" ? "error" : type === "warning" ? "warning" : ""}`;
  const heading = document.createElement("strong");
  heading.textContent = title;
  node.append(heading);
  if (text) {
    const p = document.createElement("p");
    p.textContent = text;
    node.append(p);
  }
  if (action) {
    const p = document.createElement("p");
    p.textContent = action;
    node.append(p);
  }
  return node;
}

function renderFilterButtons(stats) {
  els.resultTools.hidden = !stats.errors;
  if (!stats.errors) {
    els.filterButtons.innerHTML = "";
    return;
  }
  const filters = [
    ["all", `Все ${stats.total}`],
    ...(stats.errors ? [["errors", `Только ошибки ${stats.errors}`]] : []),
    ["ready", `Только готовые ${stats.ready}`],
  ];
  if (!filters.some(([key]) => key === state.activeFilter)) state.activeFilter = "all";
  els.filterButtons.innerHTML = "";
  filters.forEach(([key, label]) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `filter-button ${state.activeFilter === key ? "active" : ""}`;
    button.textContent = label;
    button.addEventListener("click", () => {
      state.activeFilter = key;
      state.resultLimit = 160;
      renderResults(state.lastValidation);
      renderFilterButtons(getValidationStats(state.lastValidation));
    });
    els.filterButtons.append(button);
  });
}

function renderResults(validation) {
  els.resultsArea.innerHTML = "";
  if (!validation) {
    els.resultsArea.append(createIssueCard("Проверка ещё не выполнена", "После проверки здесь появятся найденные документы и ошибки.", "", "info"));
    return;
  }
  (validation.blocking_errors || [])
    .filter((error) => error.includes("меток") || error.includes("метки"))
    .slice(0, 5)
    .forEach((error) => {
      els.resultsArea.append(
        createIssueCard(
          "Не совпадает количество документов и меток",
          error,
          "Добавьте недостающие метки или отключите нанесение номеров.",
          "error",
        ),
      );
    });
  if (validation.mode === "excel") {
    renderExcelResults(validation);
    return;
  }
  renderTextResults(validation);
}

function renderTextResults(validation) {
  const stats = getValidationStats(validation);
  const filtered = filterEntries(validation.entries || []);
  if (!stats.errors) return;
  renderEntriesTable(filtered, "text");
}

function renderExcelResults(validation) {
  const groups = (validation.groups || []).filter((group) => {
    const entries = group.validation?.entries || [];
    if (state.activeFilter === "errors") return entries.some((entry) => entry.blocking);
    if (state.activeFilter === "ready") return entries.every((entry) => !entry.blocking);
    const query = els.resultSearch.value.trim().toLocaleLowerCase("ru");
    if (!query) return true;
    return [group.title, ...entries.flatMap((entry) => [entry.number, entry.matched_file])]
      .filter(Boolean)
      .some((value) => String(value).toLocaleLowerCase("ru").includes(query));
  });
  const table = document.createElement("div");
  table.className = "table-wrap";
  const rows = groups.map((group, index) => excelGroupRow(group, index)).join("");
  table.innerHTML = `
    <table>
      <thead>
        <tr>
          <th>PDF</th>
          <th style="width: 140px">Документов</th>
          <th style="width: 150px">Статус</th>
          <th style="width: 130px"></th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  `;
  els.resultsArea.append(table);

  const cards = document.createElement("div");
  cards.className = "card-list";
  groups.forEach((group, index) => cards.append(excelGroupCard(group, index)));
  els.resultsArea.append(cards);

  groups.forEach((group, index) => {
    const button = table.querySelector(`[data-expand-group="${index}"]`);
    button?.addEventListener("click", () => toggleGroup(group.id || String(index)));
    if (state.expandedGroups.has(group.id || String(index))) {
      const filtered = filterEntries(group.validation.entries || []);
      renderEntriesTable(filtered, "excel", group.title);
    }
  });
}

function excelGroupRow(group, index) {
  const entries = group.validation?.entries || [];
  const errors = entries.filter((entry) => entry.blocking).length;
  const warnings = entries.filter((entry) => entry.warnings?.length).length;
  const found = entries.filter((entry) => entry.doc_id).length;
  const statusClass = errors ? "bad" : warnings ? "warn" : "good";
  const status = errors ? `${errors} ошибок` : warnings ? `${warnings} предупреждений` : "Готов";
  const expanded = state.expandedGroups.has(group.id || String(index));
  return `
    <tr>
      <td class="truncate" title="${escapeAttr(group.title)}">${escapeHtml(group.title)}</td>
      <td>${found}</td>
      <td><span class="badge ${statusClass}">${escapeHtml(status)}</span></td>
      <td><button class="row-action secondary" type="button" data-expand-group="${index}">${expanded ? "Скрыть" : "Подробнее"}</button></td>
    </tr>
  `;
}

function excelGroupCard(group, index) {
  const entries = group.validation?.entries || [];
  const errors = entries.filter((entry) => entry.blocking).length;
  const found = entries.filter((entry) => entry.doc_id).length;
  const node = document.createElement("article");
  node.className = "mobile-card";
  node.innerHTML = `
    <strong>${escapeHtml(group.title)}</strong>
    <span>Документов: ${found}</span>
    <span class="badge ${errors ? "bad" : "good"}">${errors ? `${errors} ошибок` : "Готов"}</span>
  `;
  const button = document.createElement("button");
  button.type = "button";
  button.className = "secondary";
  button.textContent = state.expandedGroups.has(group.id || String(index)) ? "Скрыть строки" : "Показать строки";
  button.addEventListener("click", () => toggleGroup(group.id || String(index)));
  node.append(button);
  return node;
}

function toggleGroup(groupId) {
  if (state.expandedGroups.has(groupId)) state.expandedGroups.delete(groupId);
  else state.expandedGroups.add(groupId);
  renderResults(state.lastValidation);
}

function filterEntries(entries) {
  const query = els.resultSearch.value.trim().toLocaleLowerCase("ru");
  return entries.filter((entry) => {
    if (state.activeFilter === "errors" && !entry.blocking) return false;
    if (state.activeFilter === "ready" && entry.blocking) return false;
    if (!query) return true;
    return [entry.number, entry.matched_file, entry.error, entry.status]
      .filter(Boolean)
      .some((value) => String(value).toLocaleLowerCase("ru").includes(query));
  });
}

function renderEntriesTable(entries, mode, title = "") {
  const shown = entries.slice(0, state.resultLimit);
  const wrap = document.createElement("div");
  wrap.className = "table-wrap";
  const heading = title ? `<caption>${escapeHtml(title)}</caption>` : "";
  const rows = shown.map(entryRow).join("");
  wrap.innerHTML = `
    <table>
      ${heading}
      <thead>
        <tr>
          <th style="width: 70px">№</th>
          <th style="width: 140px">Номер</th>
          <th>Документ</th>
          <th style="width: 170px">Наносимая метка</th>
          <th style="width: 180px">Статус</th>
          <th style="width: 90px">Страниц</th>
          <th style="width: 180px">Размер</th>
        </tr>
      </thead>
      <tbody>${rows || `<tr><td colspan="7">Нет строк по выбранному фильтру.</td></tr>`}</tbody>
    </table>
  `;
  els.resultsArea.append(wrap);

  const cards = document.createElement("div");
  cards.className = "card-list";
  shown.forEach((entry) => cards.append(entryCard(entry)));
  els.resultsArea.append(cards);

  if (entries.length > shown.length) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "secondary load-more";
    button.textContent = `Показать ещё ${Math.min(200, entries.length - shown.length)}`;
    button.addEventListener("click", () => {
      state.resultLimit += 200;
      renderResults(state.lastValidation);
    });
    els.resultsArea.append(button);
  }
}

function entryRow(entry) {
  const statusClass = entry.blocking ? "bad" : entry.warnings?.length ? "warn" : "good";
  const statusText = entry.blocking ? "Ошибка" : entry.warnings?.length ? "Предупреждение" : "Готово";
  const explanation = entry.error || entry.warnings?.[0] || entry.status;
  return `
    <tr>
      <td>${entry.order}</td>
      <td>${escapeHtml(entry.number)}</td>
      <td class="truncate" title="${escapeAttr(entry.matched_file || "")}">${escapeHtml(entry.matched_file || "—")}</td>
      <td class="truncate" title="${escapeAttr(entry.stamp_label || "")}">${escapeHtml(entry.stamp_label || "—")}</td>
      <td><span class="badge ${statusClass}">${statusText}</span><br><small>${escapeHtml(explanation || "")}</small></td>
      <td>${entry.pages ?? "—"}</td>
      <td class="truncate" title="${escapeAttr(entry.page_size || "")}">${escapeHtml(entry.page_size || "—")}</td>
    </tr>
  `;
}

function entryCard(entry) {
  const statusClass = entry.blocking ? "bad" : entry.warnings?.length ? "warn" : "good";
  const node = document.createElement("article");
  node.className = "mobile-card";
  node.innerHTML = `
    <strong>${entry.order}. ${escapeHtml(entry.number)}</strong>
    <span>${escapeHtml(entry.matched_file || "Документ не найден")}</span>
    <span>Метка: ${escapeHtml(entry.stamp_label || "—")}</span>
    <span class="badge ${statusClass}">${entry.blocking ? "Ошибка" : entry.warnings?.length ? "Предупреждение" : "Готово"}</span>
    <small>${escapeHtml(entry.error || entry.warnings?.[0] || entry.page_size || "")}</small>
  `;
  return node;
}

async function buildJob() {
  if (!state.jobId || !state.canBuild) return;
  const previousText = els.buildButton.textContent;
  els.buildButton.textContent = "Запускаем…";
  els.buildButton.disabled = true;
  setStep("result");
  showProgress({ percent: 0, done: 0, total: getValidationStats(state.lastValidation).total, message: "Сборка запущена" });
  try {
    const response = await fetch(`/api/print/jobs/${state.jobId}/build`, { method: "POST" });
    const data = await readJson(response);
    if (!response.ok) throw new Error(data.detail || "Не удалось запустить сборку");
    state.lastJob = { ...(state.lastJob || {}), status: "converting", build: data };
    showProgress(data);
    startPolling();
  } catch (error) {
    els.buildButton.textContent = previousText;
    els.buildButton.disabled = false;
    renderValidation(state.lastValidation);
    addInlineNotice(error.message, "error");
    setStep("check");
  }
}

function showProgress(build) {
  els.progressPanel.hidden = false;
  els.resultPanel.hidden = true;
  const percent = Number(build?.percent || 0);
  els.progressBar.style.width = `${Math.max(0, Math.min(100, percent))}%`;
  const done = build?.done ?? 0;
  const total = build?.total ?? 0;
  const pipeline = [els.pipelineCheck, els.pipelineConvert, els.pipelineMerge, els.pipelineDownload];
  const activeIndex = percent >= 99 ? 3 : percent >= 88 ? 2 : 1;
  pipeline.forEach((item, index) => {
    item?.classList.toggle("done", index < activeIndex || percent >= 100);
    item?.classList.toggle("active", index === activeIndex && percent < 100);
  });
  els.progressText.textContent = `Готово: ${done} из ${total} документов (${Math.round(percent)}%)`;
  els.progressDetails.innerHTML = "";
  if (build?.total_groups) {
    const current = Math.min(build.total_groups, (build.done_groups || 0) + 1);
    els.progressDetails.innerHTML = `<span>Сейчас обрабатывается: PDF ${current} из ${build.total_groups}</span>`;
  }
}

function startPolling() {
  stopPolling();
  state.pollTimer = window.setInterval(() => {
    refreshJob().catch(handlePollingError);
  }, 3000);
}

function stopPolling() {
  if (state.pollTimer) {
    window.clearInterval(state.pollTimer);
    state.pollTimer = null;
  }
}

function handlePollingError() {
  if (!state.connectionLost) {
    state.connectionLost = true;
    showToast("Нет связи с сервером. Пытаемся подключиться повторно…");
  }
}

async function refreshJob({ renderTable = false } = {}) {
  if (!state.jobId) return null;
  const response = await fetch(`/api/print/jobs/${state.jobId}`);
  if (!response.ok) throw new Error("Задание не найдено или срок хранения истёк");
  const job = await readJson(response);
  if (state.connectionLost) {
    state.connectionLost = false;
    showToast("Связь восстановлена");
  }
  state.lastJob = job;
  if (!registrationExternalNumbers().length && job.registration_external_numbers?.length) {
    els.registrationExternalInput.value = job.registration_external_numbers.join("\n");
    updateRegistrationExternalCount();
  }
  if (job.validation) {
    state.lastValidation = job.validation;
    state.mode = ["excel", "registration"].includes(job.validation.mode) ? job.validation.mode : state.mode || "text";
    state.registrationPreview = job.registration || state.registrationPreview;
    state.canBuild = job.validation.can_build;
    persistState();
    hydrateStampingUi(job.validation);
    renderValidation(job.validation);
  }
  renderUploadSummary(job);
  renderModePanels();
  if (job.status === "converting") {
    setStep("result");
    showProgress(job.build);
    startPolling();
  } else if (job.status === "ready") {
    stopPolling();
    renderResult(job);
    setStep("result");
  } else if (job.status === "failed") {
    stopPolling();
    els.progressPanel.hidden = true;
    els.resultPanel.hidden = true;
    renderValidation(job.validation || state.lastValidation);
    addInlineNotice(job.error || job.build?.error || "Сборка завершилась ошибкой.", "error");
    setStep("check");
  } else if (job.validation && renderTable) {
    setStep("check");
  } else if (job.status === "uploaded") {
    setStep("order");
  }
  updateHeader();
  return job;
}

function renderResult(job) {
  els.progressPanel.hidden = true;
  els.resultPanel.hidden = false;
  const build = job.build || {};
  const isExcel = Boolean(job.result_zip);
  const pdfCount = isExcel ? build.zip?.pdf_count || build.result_pdfs?.length || 0 : 1;
  const pages = isExcel ? build.zip?.page_count || 0 : build.merge?.page_count || 0;
  const size = isExcel ? build.zip?.size_bytes || 0 : build.merge?.size_bytes || 0;
  const stampApplied = build.stamping?.applied || 0;
  const singlePdfName = job.result_pdf_download_name || build.result_pdfs?.[0]?.download_name || "PDF";
  els.resultTitle.textContent = isExcel ? `✓ Готово ${pdfCount} PDF` : `✓ ${singlePdfName} готов`;
  els.resultMetrics.innerHTML = `
    <div class="metric"><span>Страниц</span><strong>${pages}</strong></div>
    <div class="metric"><span>Размер</span><strong>${formatBytes(size)}</strong></div>
    ${stampApplied ? `<div class="metric"><span>Номеров нанесено</span><strong>${stampApplied}</strong></div>` : ""}
  `;
  const primaryHref = isExcel ? `/api/print/jobs/${job.id}/download/zip` : `/api/print/jobs/${job.id}/download/pdf`;
  const primaryText = isExcel ? `Скачать ZIP с ${pdfCount} PDF` : `Скачать ${singlePdfName}`;
  const reportLink = job.report_csv
    ? `<a class="download secondary-link" href="/api/print/jobs/${job.id}/download/report.csv">Скачать отчёт CSV</a>`
    : "";
  const mappingLink = job.number_mapping_xlsx
    ? `<a class="download secondary-link" href="/api/print/jobs/${job.id}/download/number-mapping.xlsx">Скачать Excel-сопоставление</a>`
    : "";
  const html = `
    <a class="download primary-download" href="${primaryHref}">${primaryText}</a>
    ${mappingLink}
    ${reportLink}
    <button class="secondary" type="button" data-result-new-task>Создать новую задачу</button>
  `;
  els.resultBlock.innerHTML = html;
  els.downloadTitle.textContent = isExcel ? `Готово ${pdfCount} PDF` : singlePdfName;
  els.downloadActions.innerHTML = `<a class="download primary-download" href="${primaryHref}">${primaryText}</a>${mappingLink}`;
  els.resultBlock.querySelector("[data-result-new-task]")?.addEventListener("click", () => els.newTaskButton.click());
  renderPartsList(job);
}

function renderPartsList(job) {
  els.partsList.innerHTML = "";
  const parts = job.build?.result_pdfs || [];
  if (!parts.length || !job.result_zip) return;
  const title = document.createElement("h3");
  title.textContent = job.build?.mode === "registration" ? "PDF по партиям" : "PDF по столбцам";
  els.partsList.append(title);
  parts.forEach((part, index) => {
    const row = document.createElement("div");
    row.className = "part-row";
    row.innerHTML = `
      <strong title="${escapeAttr(part.download_name)}">${escapeHtml(part.download_name)}</strong>
      <span>${escapeHtml(part.title || "PDF")} · ${part.page_count} ${plural(part.page_count, "страница", "страницы", "страниц")}</span>
      <a class="download secondary-link" href="/api/print/jobs/${job.id}/download/part/${index + 1}">Скачать</a>
    `;
    els.partsList.append(row);
  });
}

function flatEntries(validation) {
  if (validation?.mode === "excel") {
    return validation.groups.flatMap((group) => group.validation?.entries || []);
  }
  return validation?.entries || [];
}

function plural(count, one, few, many) {
  const mod10 = count % 10;
  const mod100 = count % 100;
  if (mod10 === 1 && mod100 !== 11) return one;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return few;
  return many;
}

function formatBytes(bytes) {
  if (!bytes) return "0 Б";
  const units = ["Б", "КБ", "МБ", "ГБ"];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(value >= 10 || unit === 0 ? 0 : 1)} ${units[unit]}`;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function escapeAttr(value) {
  return escapeHtml(value).replaceAll("`", "&#096;");
}

function askConfirm({ title, text, okText = "Продолжить", danger = false }) {
  return new Promise((resolve) => {
    els.confirmTitle.textContent = title;
    els.confirmText.textContent = text;
    els.confirmOkButton.textContent = okText;
    els.confirmOkButton.classList.toggle("danger", danger);
    els.confirmAltButton.hidden = true;
    const onClose = () => {
      els.confirmDialog.removeEventListener("close", onClose);
      resolve(els.confirmDialog.returnValue === "ok");
    };
    els.confirmDialog.addEventListener("close", onClose);
    els.confirmDialog.showModal();
  });
}

function askListMergeChoice() {
  return new Promise((resolve) => {
    els.confirmTitle.textContent = "Как загрузить дополнительные списки?";
    els.confirmText.textContent = "В поле уже есть номера. Можно добавить новые строки в конец или полностью заменить текущий список.";
    els.confirmOkButton.textContent = "Добавить к списку";
    els.confirmOkButton.classList.remove("danger");
    els.confirmAltButton.textContent = "Заменить список";
    els.confirmAltButton.hidden = false;
    const onClose = () => {
      els.confirmDialog.removeEventListener("close", onClose);
      els.confirmAltButton.hidden = true;
      if (els.confirmDialog.returnValue === "ok") resolve("append");
      else if (els.confirmDialog.returnValue === "alt") resolve("replace");
      else resolve("cancel");
    };
    els.confirmDialog.addEventListener("close", onClose);
    els.confirmDialog.showModal();
  });
}

async function startNewTask() {
  if (state.lastJob?.status === "ready") {
    const ok = await askConfirm({
      title: "Начать новую задачу?",
      text: "Текущий результат останется доступен до окончания срока хранения.",
      okText: "Начать новую",
    });
    if (!ok) return;
  } else if (state.lastJob?.status === "converting") {
    const ok = await askConfirm({
      title: "Сборка ещё выполняется",
      text: "Новая задача не остановит текущую обработку. Вы сможете вернуться к ней по последнему заданию.",
      okText: "Начать новую",
    });
    if (!ok) return;
  }
  if (state.jobId) {
    localStorage.setItem(STORAGE.skipRecent, state.jobId);
  }
  forgetLocalTask();
  renderUploadSummary(null);
  renderModePanels();
  els.validationSummary.innerHTML = "";
  els.warningGroups.innerHTML = "";
  els.resultsArea.innerHTML = "";
  els.resultPanel.hidden = true;
  els.progressPanel.hidden = true;
  els.downloadBar.hidden = true;
  setStep("documents");
}

async function deleteCurrentTask() {
  if (!state.jobId) return;
  const ok = await askConfirm({
    title: "Удалить текущую задачу?",
    text: "Файлы результата и отчёта будут удалены с сервера.",
    okText: "Удалить",
    danger: true,
  });
  if (!ok) return;
  await fetch(`/api/print/jobs/${state.jobId}`, { method: "DELETE" }).catch(() => {});
  forgetLocalTask();
  window.location.reload();
}

function showTaskDetails() {
  const job = state.lastJob || {};
  const build = job.build || {};
  const validation = job.validation || state.lastValidation;
  const stats = validation ? getValidationStats(validation) : null;
  const size = job.result_zip ? build.zip?.size_bytes : build.merge?.size_bytes;
  const rows = [
    ["ID", job.id || state.jobId || "—"],
    ["Статус", readableStatus(job.status)],
    ["Создано", formatDate(job.created_at)],
    ["Режим", validation?.mode === "excel" ? "Excel" : state.mode === "text" ? "Один список" : "—"],
    ["DOCX", job.documents?.length ?? "—"],
    ["PDF", stats?.pdfCount ?? "—"],
    ["Страниц", job.result_zip ? build.zip?.page_count ?? "—" : build.merge?.page_count ?? "—"],
    ["Размер", size ? formatBytes(size) : "—"],
    ["Хранение", "до окончания срока хранения сервера"],
  ];
  els.taskDetails.innerHTML = "";
  rows.forEach(([label, value]) => {
    const row = document.createElement("div");
    row.className = "detail-row";
    row.innerHTML = `<span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong>`;
    els.taskDetails.append(row);
  });
  els.detailsDialog.showModal();
}

function showFiles() {
  const docs = state.lastJob?.documents || [];
  els.filesList.innerHTML = "";
  if (!docs.length) {
    els.filesList.textContent = "Здесь появятся загруженные документы.";
  } else {
    docs.slice(0, 500).forEach((doc, index) => {
      const row = document.createElement("div");
      row.className = "file-row";
      row.innerHTML = `<strong title="${escapeAttr(doc.original_name)}">${index + 1}. ${escapeHtml(doc.original_name)}</strong><span>${formatBytes(doc.size_bytes || 0)}</span>`;
      els.filesList.append(row);
    });
    if (docs.length > 500) {
      const more = document.createElement("p");
      more.textContent = `Показано 500 из ${docs.length}. Полный список есть в отчёте CSV.`;
      els.filesList.append(more);
    }
  }
  els.filesDialog.showModal();
}

function readableStatus(status) {
  return {
    uploaded: "Документы загружены",
    validated: "Проверено",
    converting: "Собирается",
    ready: "Готово",
    failed: "Ошибка",
    expired: "Истекло",
  }[status] || "—";
}

async function handleStampXlsxUpload() {
  const file = els.stampXlsxInput.files[0];
  if (!file || !state.jobId) return;
  const formData = new FormData();
  formData.append("file", file);
  try {
    const response = await fetch(`/api/print/jobs/${state.jobId}/stamping/xlsx`, {
      method: "POST",
      body: formData,
    });
    const data = await readJson(response);
    if (!response.ok) throw new Error(data.detail || "Не удалось прочитать Excel с метками");
    renderStampColumnChoice(file, data.columns || []);
  } catch (error) {
    showToast(error.message);
  }
}

function renderStampColumnChoice(file, columns) {
  els.stampWarnings.innerHTML = "";
  if (!columns.length) {
    els.stampWarnings.append(createIssueCard("В Excel не найдено меток", "Выберите другой файл или вставьте список вручную.", "", "error"));
    return;
  }
  const card = document.createElement("article");
  card.className = "issue-card";
  const options = columns
    .map((column) => `<option value="${escapeAttr(column.column)}">${escapeHtml(column.column)}</option>`)
    .join("");
  card.innerHTML = `
    <strong>Файл с номерами для нанесения: ${escapeHtml(file.name)}</strong>
    <p data-stamp-column-summary></p>
    <select data-stamp-column-choice>${options}</select>
    <button class="secondary" type="button" data-load-stamp-column>Загрузить номера</button>
  `;
  els.stampWarnings.append(card);
  const select = card.querySelector("[data-stamp-column-choice]");
  const renderChoiceSummary = () => {
    const selected = columns.find((column) => String(column.column) === select.value) || columns[0];
    card.querySelector("[data-stamp-column-summary]").textContent = `Столбец: ${selected.column} · Количество значений: ${selected.count} · Первый номер: ${selected.first || "—"}`;
  };
  select.addEventListener("change", renderChoiceSummary);
  renderChoiceSummary();
  card.querySelector("[data-load-stamp-column]").addEventListener("click", async () => {
    const column = select.value;
    const formData = new FormData();
    formData.append("file", file);
    formData.append("column", column);
    formData.append("purpose", "external_military");
    const response = await fetch(`/api/print/jobs/${state.jobId}/stamping/xlsx`, {
      method: "POST",
      body: formData,
    });
    const data = await readJson(response);
    if (!response.ok) {
      showToast(data.detail || "Не удалось загрузить столбец");
      return;
    }
    const text = (data.labels || []).join("\n");
    if (state.mode === "excel" && state.lastValidation?.groups?.length) {
      const firstGroup = els.stampExcelGroups.querySelector("[data-stamp-group-text]");
      if (firstGroup) firstGroup.value = text;
    } else {
      els.stampTextInput.value = text;
    }
    markStampAssignmentDirty();
    showToast(`Загружен столбец ${column}: ${data.labels?.length || 0} значений`);
    updateStampSummary();
  });
}

function applyRegistrationExternalNumbersFromExcel(file, data) {
  const labels = data.all_labels || data.labels || [];
  els.registrationExternalWarnings.innerHTML = "";
  if (!labels.length) {
    els.registrationExternalWarnings.append(createIssueCard("В Excel не найдено номеров", "Выберите другой файл или вставьте список вручную.", "", "error"));
    return;
  }
  els.registrationExternalInput.value = labels.join("\n");
  updateRegistrationExternalCount();
  resetRegistrationPreview();
  const columns = data.columns || [];
  const firstColumn = columns[0]?.column || "—";
  const lastColumn = columns[columns.length - 1]?.column || firstColumn;
  els.registrationExternalWarnings.append(
    createIssueCard(
      "Excel-список загружен",
      `Загружено ${labels.length} номеров из ${columns.length || 1} колонок: ${firstColumn}${lastColumn !== firstColumn ? `–${lastColumn}` : ""}. Номера идут по колонкам сверху вниз.`,
      "",
      "ok",
    )
  );
  showToast(`Excel № в в/ч №522: ${labels.length} номеров`);
}

function renderRegistrationExternalColumnChoice(file, columns) {
  els.registrationExternalWarnings.innerHTML = "";
  if (!columns.length) {
    els.registrationExternalWarnings.append(createIssueCard("В Excel не найдено номеров", "Выберите другой файл или вставьте список вручную.", "", "error"));
    return;
  }
  const card = document.createElement("article");
  card.className = "issue-card";
  const options = columns
    .map((column) => `<option value="${escapeAttr(column.column)}">${escapeHtml(column.column)} · ${column.count} значений · первый: ${escapeHtml(column.first)}</option>`)
    .join("");
  card.innerHTML = `
    <strong>Выберите столбец с № в в/ч №522</strong>
    <p>${escapeHtml(file.name)}</p>
    <select data-registration-external-column>${options}</select>
    <button class="secondary" type="button" data-load-registration-external-column>Загрузить выбранный столбец</button>
  `;
  els.registrationExternalWarnings.append(card);
  card.querySelector("[data-load-registration-external-column]").addEventListener("click", async () => {
    const column = card.querySelector("[data-registration-external-column]").value;
    const formData = new FormData();
    formData.append("file", file);
    formData.append("column", column);
    formData.append("purpose", "external_military");
    const response = await fetch(`/api/print/jobs/${state.jobId}/stamping/xlsx`, {
      method: "POST",
      body: formData,
    });
    const data = await readJson(response);
    if (!response.ok) {
      showToast(data.detail || "Не удалось загрузить столбец");
      return;
    }
    applyRegistrationExternalNumbersFromExcel(file, data);
    showToast(`Загружен столбец ${column}: ${data.labels?.length || 0} значений`);
  });
}

async function handleRegistrationExternalXlsxUpload() {
  const file = els.registrationExternalXlsxInput.files[0];
  if (!file || !state.jobId) return;
  await loadRegistrationExternalXlsxFile(file);
}

async function loadSelectedExcelAsRegistrationExternalNumbers() {
  if (!state.jobId || !state.excelFile || state.mode !== "registration") return;
  if (registrationExternalNumbers().length) return;
  await loadRegistrationExternalXlsxFile(state.excelFile);
}

async function loadRegistrationExternalXlsxFile(file) {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("purpose", "external_military");
  try {
    const response = await fetch(`/api/print/jobs/${state.jobId}/stamping/xlsx`, {
      method: "POST",
      body: formData,
    });
    const data = await readJson(response);
    if (!response.ok) throw new Error(data.detail || "Не удалось прочитать Excel с номерами");
    applyRegistrationExternalNumbersFromExcel(file, data);
    state.registrationExternalLoadedFileKey = fileKey(file);
  } catch (error) {
    showToast(error.message);
  }
}

function formatDate(value) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("ru-RU", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(new Date(value));
}

async function restorePreviousJob() {
  els.sequenceInput.value = localStorage.getItem(STORAGE.sequence) || "";
  state.mode = localStorage.getItem(STORAGE.mode) || null;
  updateSequenceCount();
  const storedJobId = localStorage.getItem(STORAGE.jobId);
  if (storedJobId) {
    state.jobId = storedJobId;
    try {
      await refreshJob({ renderTable: true });
      showToast(state.lastJob?.status === "ready" ? "Задание восстановлено. Результат уже готов." : "Задание восстановлено");
      return;
    } catch {
      forgetLocalTask();
    }
  }
  try {
    const response = await fetch("/api/print/jobs/recent");
    if (!response.ok) throw new Error("Нет последнего задания");
    const job = await readJson(response);
    if (job.id === localStorage.getItem(STORAGE.skipRecent)) {
      throw new Error("Последняя задача скрыта для новой сессии");
    }
    if (!["converting", "ready"].includes(job.status)) throw new Error("Нет активного результата");
    setJobId(job.id);
    state.lastJob = job;
    await refreshJob({ renderTable: true });
    showToast(job.status === "converting" ? "Задание восстановлено. Сборка продолжалась в фоне." : "Задание восстановлено. Результат уже готов.");
  } catch {
    renderUploadSummary(null);
    renderModePanels();
    updateHeader();
    setStep("documents");
  }
}

els.selectFilesButton.addEventListener("click", () => els.fileInput.click());
els.fileInput.addEventListener("change", () => {
  if (els.fileInput.files.length) queueRecords([...els.fileInput.files].map((file) => ({ file, relativePath: file.name, source: "file" })));
  els.fileInput.value = "";
});
els.selectFolderButton.addEventListener("click", () => els.folderInput.click());
els.folderInput.addEventListener("change", () => {
  if (els.folderInput.files.length) {
    queueRecords(
      [...els.folderInput.files].map((file) => ({ file, relativePath: file.webkitRelativePath || file.name, source: "folder" })),
      { folderSelection: true },
    );
  }
  els.folderInput.value = "";
});
els.clearQueueButton.addEventListener("click", () => {
  state.pendingFiles = [];
  state.pendingSkipped = 0;
  state.pendingFolderNames.clear();
  state.excelFile = null;
  renderPendingQueue();
  renderModePanels();
});
els.uploadQueueButton.addEventListener("click", () => {
  if (!state.pendingFiles.length || pendingQueueLimitError()) return;
  uploadFiles(state.pendingFiles);
});

["dragenter", "dragover"].forEach((eventName) => {
  els.dropZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    els.dropZone.classList.add("drag-over");
  });
});

["dragleave", "drop"].forEach((eventName) => {
  els.dropZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    els.dropZone.classList.remove("drag-over");
  });
});

els.dropZone.addEventListener("drop", async (event) => {
  try {
    const records = await droppedRecords(event.dataTransfer);
    if (records.length) queueRecords(records);
  } catch (error) {
    showToast(error.message || "Не удалось прочитать папку");
  }
});

els.textModeButton.addEventListener("click", () => selectMode("text"));
els.excelModeButton.addEventListener("click", () => selectMode("excel"));
els.registrationModeButton.addEventListener("click", () => selectMode("registration"));
els.changeModeButton.addEventListener("click", () => {
  state.mode = null;
  state.registrationPreview = null;
  persistState();
  renderModePanels();
});

els.txtInput.addEventListener("change", async () => {
  await loadSequenceTxtFiles(els.txtInput.files);
  els.txtInput.value = "";
});

els.clearSequenceButton.addEventListener("click", async () => {
  const info = getSequenceInfo();
  if (info.total > 20) {
    const ok = await askConfirm({
      title: "Очистить список?",
      text: `В списке ${info.total} ${plural(info.total, "строка", "строки", "строк")}.`,
      okText: "Очистить",
    });
    if (!ok) return;
  }
  invalidateTextValidation();
  els.sequenceInput.value = "";
  state.txtFiles = [];
  state.sequenceBeforeSort = null;
  els.undoSortButton.hidden = true;
  renderTxtFilesSummary();
  updateSequenceCount();
});

els.sortSequenceButton.addEventListener("click", () => {
  sortSequenceNaturally();
});
els.undoSortButton.addEventListener("click", () => {
  undoSequenceSort();
});
els.sequenceInput.addEventListener("input", () => {
  invalidateTextValidation();
  state.sequenceBeforeSort = null;
  els.undoSortButton.hidden = true;
  updateSequenceCount();
});
els.validateButton.addEventListener("click", validateTextJob);
els.viewOrderValidationButton.addEventListener("click", () => setStep("check"));

els.stampEnabledInput.addEventListener("change", renderStampingPanel);
els.stampTextInput.addEventListener("input", () => {
  markStampAssignmentDirty();
  updateStampSummary();
});
els.stampStartNumberInput.addEventListener("input", () => {
  markStampAssignmentDirty();
  updateStampSummary();
});
els.useManualStampButton.addEventListener("click", () => setStampSourceMode("manual"));
els.useAutoStampButton.addEventListener("click", () => setStampSourceMode("auto_sequence"));
els.showGeneratedNumbersButton.addEventListener("click", () => {
  els.stampGeneratedPreview.hidden = !els.stampGeneratedPreview.hidden;
  els.showGeneratedNumbersButton.textContent = els.stampGeneratedPreview.hidden ? "Показать список" : "Скрыть список";
  updateStampSummary();
});
els.stampRejectDuplicatesInput.addEventListener("change", updateStampSummary);
els.stampAllowSkipInput.addEventListener("change", updateStampSummary);
[
  els.stampCornerInput,
  els.stampRotationInput,
  els.stampMarginXInput,
  els.stampMarginYInput,
  els.stampFontSizeInput,
  els.stampBoldInput,
  els.stampBackgroundInput,
  els.stampBorderInput,
].forEach((input) => input.addEventListener("change", updateStampSummary));
els.stampTxtInput.addEventListener("change", async () => {
  const file = els.stampTxtInput.files[0];
  if (!file) return;
  els.stampTextInput.value = await file.text();
  markStampAssignmentDirty();
  updateStampSummary();
  showToast("Список меток TXT загружен");
});
els.stampXlsxInput.addEventListener("change", handleStampXlsxUpload);
els.clearStampButton.addEventListener("click", () => {
  els.stampTextInput.value = "";
  els.stampExcelGroups.querySelectorAll("[data-stamp-group-text]").forEach((node) => {
    node.value = "";
  });
  markStampAssignmentDirty();
  updateStampSummary();
});
els.applyStampingButton.addEventListener("click", applyStampingToCurrentValidation);
els.stampPreviewButton.addEventListener("click", showStampPreview);

els.xlsxInput.addEventListener("change", () => {
  state.excelFile = els.xlsxInput.files[0] || null;
  renderExcelState();
  if (state.excelFile) showToast("Excel выбран");
});

els.validateExcelButton.addEventListener("click", validateExcelJob);
[
  els.registrationStartPartyInput,
  els.registrationYearInput,
  els.registrationPerPartyInput,
  els.registrationStartRcsmeInput,
  els.registrationIntakeDateInput,
  els.registrationDecisionDateInput,
  els.registrationInvestigatorInput,
  els.registrationIncomingInput,
  els.registrationBoxInput,
].forEach((input) => {
  input.addEventListener("input", () => {
    resetRegistrationPreview();
  });
});
els.registrationExternalInput.addEventListener("input", () => {
  updateRegistrationExternalCount();
  resetRegistrationPreview();
});
els.registrationExternalTxtInput.addEventListener("change", async () => {
  const file = els.registrationExternalTxtInput.files[0];
  if (!file) return;
  els.registrationExternalInput.value = await file.text();
  updateRegistrationExternalCount();
  resetRegistrationPreview();
  showToast("Список № в в/ч №522 TXT загружен");
});
els.registrationExternalXlsxInput.addEventListener("change", handleRegistrationExternalXlsxUpload);
els.clearRegistrationExternalButton.addEventListener("click", () => {
  els.registrationExternalInput.value = "";
  els.registrationExternalWarnings.innerHTML = "";
  updateRegistrationExternalCount();
  resetRegistrationPreview();
});
els.previewRegistrationButton.addEventListener("click", previewAutoRegistration);
els.applyRegistrationButton.addEventListener("click", applyAutoRegistration);
els.resultSearch.addEventListener("input", () => {
  state.resultLimit = 160;
  renderResults(state.lastValidation);
});
els.buildButton.addEventListener("click", buildJob);
els.newTaskButton.addEventListener("click", startNewTask);
els.showFilesButton.addEventListener("click", showFiles);
els.menuButton.addEventListener("click", () => {
  const open = els.taskMenu.hidden;
  els.taskMenu.hidden = !open;
  els.menuButton.setAttribute("aria-expanded", String(open));
});
els.menuDetailsButton.addEventListener("click", () => {
  els.taskMenu.hidden = true;
  showTaskDetails();
});
els.menuPrintButton.addEventListener("click", () => {
  els.taskMenu.hidden = true;
  if (state.lastJob?.status !== "ready") {
    showToast("Справка о печати появится после сборки PDF");
    return;
  }
  setStep("result");
  document.querySelector(".print-advice")?.scrollIntoView({ behavior: "smooth", block: "center" });
});
els.menuDeleteButton.addEventListener("click", () => {
  els.taskMenu.hidden = true;
  deleteCurrentTask();
});
document.addEventListener("click", (event) => {
  if (!els.taskMenu.hidden && !event.target.closest(".menu-wrap")) {
    els.taskMenu.hidden = true;
    els.menuButton.setAttribute("aria-expanded", "false");
  }
});
els.stepItems.forEach((item) => {
  item.addEventListener("click", () => {
    if (!item.disabled) setStep(item.dataset.step);
  });
});

if (!els.registrationYearInput.value) {
  els.registrationYearInput.value = String(new Date().getFullYear());
}
restoreStampUiSettings();
renderPendingQueue();
renderTxtFilesSummary();
restorePreviousJob();
