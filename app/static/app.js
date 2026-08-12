const overlay = document.querySelector("#progress-overlay");
const statusLabel = document.querySelector("#status-label");
const statusMessage = document.querySelector("#status-message");
const progressLabel = document.querySelector("#progress-label");
const progressBar = document.querySelector("#progress-bar");
const progressTrack = document.querySelector(".progress-track");

let pollFailureCount = 0;
let pollTimer = null;

const statusNames = {
  queued: "Na fila",
  running: "Em andamento",
  completed: "Concluído",
  failed: "Erro",
};

const terminalStatuses = new Set(["completed", "failed"]);

function clearPollTimer() {
  if (pollTimer) {
    window.clearTimeout(pollTimer);
    pollTimer = null;
  }
}

function showOverlay() {
  if (!overlay) return;
  overlay.hidden = false;
  overlay.setAttribute("aria-hidden", "false");
  document.body.classList.add("progress-active");
}

function hideOverlay() {
  if (!overlay) return;
  overlay.hidden = true;
  overlay.setAttribute("aria-hidden", "true");
  document.body.classList.remove("progress-active");
}

function updateStatus(task) {
  const progress = Math.max(0, Math.min(100, task.progress || 0));
  statusLabel.textContent = statusNames[task.status] || task.status;
  statusMessage.textContent = task.error || task.message || "";
  progressLabel.textContent = `${progress}%`;
  progressBar.style.width = `${progress}%`;
  progressTrack.setAttribute("aria-valuenow", String(progress));
}

async function readError(response) {
  try {
    const data = await response.json();
    const detail = data.detail;
    if (Array.isArray(detail)) {
      return detail[0]?.msg?.replace(/^Value error, /, "") || "Dados inválidos.";
    }
    return detail || "Ocorreu um erro inesperado.";
  } catch {
    return "O servidor não respondeu como esperado.";
  }
}

async function pollTask(taskId) {
  try {
    const response = await fetch(`/api/tasks/${encodeURIComponent(taskId)}`, {
      credentials: "same-origin",
    });
    if (response.status === 404) {
      updateStatus({
        status: "failed",
        progress: 100,
        message: "Esta tarefa não existe mais. O servidor pode ter reiniciado.",
      });
      return;
    }
    if (!response.ok) throw new Error(await readError(response));

    const task = await response.json();
    pollFailureCount = 0;
    updateStatus(task);

    if (terminalStatuses.has(task.status)) {
      if (task.status === "completed" && task.redirect_url) {
        window.setTimeout(() => {
          window.location.href = task.redirect_url;
        }, 450);
      }
      return;
    }

    pollTimer = window.setTimeout(() => pollTask(taskId), 800);
  } catch {
    pollFailureCount += 1;
    const retryDelay = Math.min(1000 * pollFailureCount, 5000);
    statusLabel.textContent = "Reconectando";
    statusMessage.textContent = navigator.onLine
      ? `Não foi possível atualizar o status. Nova tentativa em ${retryDelay / 1000}s.`
      : "Sem conexão. O acompanhamento será retomado automaticamente.";
    pollTimer = window.setTimeout(() => pollTask(taskId), retryDelay);
  }
}

async function startLongTask(form) {
  clearPollTimer();
  pollFailureCount = 0;
  showOverlay();
  updateStatus({ status: "queued", progress: 0, message: "Enviando dados…" });

  const submitters = form.querySelectorAll("button, input[type='submit']");
  submitters.forEach((el) => {
    el.disabled = true;
  });

  try {
    const response = await fetch(form.action || window.location.href, {
      method: (form.method || "POST").toUpperCase(),
      body: new FormData(form),
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    });
    if (!response.ok) throw new Error(await readError(response));
    const task = await response.json();
    if (!task.task_id) throw new Error("Resposta inválida do servidor.");
    updateStatus(task);
    pollTask(task.task_id);
  } catch (error) {
    updateStatus({
      status: "failed",
      progress: 100,
      message: error.message || "Falha ao iniciar a tarefa.",
    });
    submitters.forEach((el) => {
      el.disabled = false;
    });
  }
}

document.querySelectorAll("form.js-long-task").forEach((form) => {
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const submitter = event.submitter;
    if (submitter?.dataset?.mode) {
      const modeInput = form.querySelector("#save_mode");
      if (modeInput) modeInput.value = submitter.dataset.mode;
    }
    if (form.classList.contains("js-job-form")) {
      collectJobAnalysis(form);
    }
    startLongTask(form);
  });
});

function criterionRowTemplate(name = "", weight = 3, group = "") {
  const row = document.createElement("div");
  row.className = "criteria-row";
  row.innerHTML = `
    <input type="text" class="criterion-name" value="${escapeAttr(name)}" placeholder="Nome do critério" maxlength="80">
    <label class="weight-field">Peso
      <input type="number" class="criterion-weight" min="1" max="10" step="1" value="${Number(weight) || 3}">
    </label>
    <label class="group-field">Grupo
      <input type="text" class="criterion-group" value="${escapeAttr(group)}" placeholder="Skill group" maxlength="80">
    </label>
    <button type="button" class="button secondary danger js-remove-criterion" aria-label="Remover critério">Remover</button>
  `;
  return row;
}

function escapeAttr(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll('"', "&quot;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function collectJobAnalysis(form) {
  const analysisInput = form.querySelector("#analysis_json");
  if (!analysisInput) return;

  const tierMap = {
    must_have: "MUST_HAVE",
    core_skills: "CORE",
    supporting_skills: "SUPPORTING",
    differentials: "DIFFERENTIAL",
    soft_skills: "SOFT",
  };

  const analysis = {
    must_have: [],
    core_skills: [],
    supporting_skills: [],
    differentials: [],
    soft_skills: [],
    hard_skills: [],
    desired_skills: [],
  };

  form.querySelectorAll(".criteria-list[data-category]").forEach((list) => {
    const category = list.dataset.category;
    if (!analysis[category]) return;
    list.querySelectorAll(".criteria-row").forEach((row) => {
      const name = row.querySelector(".criterion-name")?.value?.trim() || "";
      const weightRaw = row.querySelector(".criterion-weight")?.value;
      const group = row.querySelector(".criterion-group")?.value?.trim() || "";
      const weight = Number.parseInt(weightRaw, 10);
      if (!name) return;
      const item = {
        name,
        weight: Number.isFinite(weight) ? weight : 3,
        tier: tierMap[category] || "",
        group,
      };
      analysis[category].push(item);
    });
  });

  analysisInput.value = JSON.stringify(analysis);
}

function initCriteriaEditor(root = document) {
  const editor = root.querySelector("#criteria-editor");
  if (!editor) return;

  editor.querySelectorAll(".tab-btn").forEach((button) => {
    button.addEventListener("click", () => {
      const tab = button.dataset.tab;
      editor.querySelectorAll(".tab-btn").forEach((btn) => {
        const active = btn === button;
        btn.classList.toggle("is-active", active);
        btn.setAttribute("aria-selected", active ? "true" : "false");
      });
      editor.querySelectorAll(".tab-panel").forEach((panel) => {
        const active = panel.dataset.panel === tab;
        panel.classList.toggle("is-active", active);
        panel.hidden = !active;
      });
    });
  });

  editor.addEventListener("click", (event) => {
    const addBtn = event.target.closest(".js-add-criterion");
    if (addBtn) {
      const category = addBtn.dataset.category;
      const defaultWeight = Number.parseInt(addBtn.dataset.defaultWeight || "3", 10);
      const list = editor.querySelector(`.criteria-list[data-category="${category}"]`);
      if (!list) return;
      list.appendChild(criterionRowTemplate("", defaultWeight));
      list.lastElementChild?.querySelector(".criterion-name")?.focus();
      return;
    }

    const removeBtn = event.target.closest(".js-remove-criterion");
    if (removeBtn) {
      const list = removeBtn.closest(".criteria-list");
      const row = removeBtn.closest(".criteria-row");
      if (!list || !row) return;
      if (list.querySelectorAll(".criteria-row").length === 1) {
        row.querySelector(".criterion-name").value = "";
        row.querySelector(".criterion-weight").value = "3";
        const groupInput = row.querySelector(".criterion-group");
        if (groupInput) groupInput.value = "";
        return;
      }
      row.remove();
    }
  });
}

initCriteriaEditor();
