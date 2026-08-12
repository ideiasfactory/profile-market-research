(() => {
  const form = document.querySelector("#compensation-form");
  if (!form) return;

  const submitBtn = document.querySelector("#compensation-submit");
  const clearBtn = document.querySelector("#compensation-clear");
  const errorEl = document.querySelector("#compensation-error");
  const resultsEl = document.querySelector("#compensation-results");

  const overlay = document.querySelector("#progress-overlay");
  const statusLabel = document.querySelector("#status-label");
  const statusMessage = document.querySelector("#status-message");
  const progressLabel = document.querySelector("#progress-label");
  const progressBar = document.querySelector("#progress-bar");
  const progressTrack = document.querySelector(".progress-track");

  let progressValue = 0;
  let activeCacheKey = new URLSearchParams(window.location.search).get("cache_key") || "";

  const historyList = document.querySelector("#history-list");
  const historyCount = document.querySelector("#history-count");

  function money(value, unit) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
    const formatted = Number(value).toLocaleString("pt-BR", {
      style: "currency",
      currency: "BRL",
      maximumFractionDigits: 2,
    });
    if (unit === "hour") return `${formatted}/h`;
    if (unit === "month") return `${formatted}/mês`;
    return formatted;
  }

  function observedLabel(obs) {
    const salary = obs.salary || {};
    const period = salary.period || "month";
    const suffix = period === "hour" ? "/h" : period === "year" ? "/ano" : "/mês";
    if (salary.average != null) return `R$ ${Number(salary.average).toLocaleString("pt-BR")}${suffix}`;
    if (salary.min != null || salary.max != null) {
      const min = salary.min != null ? Number(salary.min).toLocaleString("pt-BR") : "?";
      const max = salary.max != null ? Number(salary.max).toLocaleString("pt-BR") : "?";
      return `R$ ${min}–${max}${suffix}`;
    }
    return "—";
  }

  function showError(message) {
    errorEl.hidden = !message;
    errorEl.textContent = message || "";
  }

  function showOverlay(message, progress = 0, status = "Pesquisando") {
    if (!overlay) return;
    overlay.hidden = false;
    overlay.setAttribute("aria-hidden", "false");
    document.body.classList.add("progress-active");
    statusLabel.textContent = status;
    statusMessage.textContent = message;
    setProgress(progress);
  }

  function setProgress(value) {
    progressValue = Math.max(0, Math.min(100, Number(value) || 0));
    progressLabel.textContent = `${progressValue}%`;
    progressBar.style.width = `${progressValue}%`;
    progressTrack?.setAttribute("aria-valuenow", String(progressValue));
  }

  function hideOverlay() {
    if (!overlay) return;
    overlay.hidden = true;
    overlay.setAttribute("aria-hidden", "true");
    document.body.classList.remove("progress-active");
  }

  function sleep(ms) {
    return new Promise((resolve) => window.setTimeout(resolve, ms));
  }

  async function pollResearchTask(taskId) {
    const response = await fetch(`/api/tasks/${encodeURIComponent(taskId)}`, {
      credentials: "same-origin",
    });
    if (response.status === 404) {
      throw new Error("A tarefa expirou ou o servidor reiniciou. Tente novamente.");
    }
    if (!response.ok) {
      throw new Error("Não foi possível acompanhar o progresso da pesquisa.");
    }
    const task = await response.json();
    const statusLabelText =
      task.status === "queued"
        ? "Na fila"
        : task.status === "running"
          ? "Em andamento"
          : task.status === "completed"
            ? "Concluído"
            : task.status === "failed"
              ? "Erro"
              : task.status;
    showOverlay(task.error || task.message || "Processando…", task.progress || 0, statusLabelText);

    if (task.status === "completed") {
      if (!task.result) throw new Error("Pesquisa concluída sem resultado.");
      return task.result;
    }
    if (task.status === "failed") {
      throw new Error(task.error || task.message || "Falha na pesquisa.");
    }
    await sleep(800);
    return pollResearchTask(taskId);
  }

  function confidenceClass(level) {
    if (level === "HIGH") return "verdict-recomendado";
    if (level === "MEDIUM") return "verdict-considerar";
    return "verdict-nao_recomendado";
  }

  function renderResults(data) {
    resultsEl.hidden = false;
    clearBtn.hidden = false;

    const market = data.market || {};
    const unit = market.unit || "hour";
    const profile = data.profile || {};
    const sample = data.sample || {};
    const confidence = data.confidence || {};
    const providers = data.providers || {};

    document.querySelector("#result-role").textContent =
      profile.normalized_role || profile.role_family || "Resultado";
    document.querySelector("#result-meta").textContent = [
      `ID ${data.research_id || "—"}`,
      market.contract_type || "",
      `search: ${(providers.search_engines_used || []).join(", ") || "nenhum"}`,
      `crawlers: ${(providers.crawlers_used || []).join(", ") || "nenhum"}`,
      data.created_at ? new Date(data.created_at).toLocaleString("pt-BR") : "",
    ]
      .filter(Boolean)
      .join(" · ");

    const badge = document.querySelector("#result-confidence");
    badge.textContent = `${confidence.level || "LOW"} · ${Math.round((confidence.score || 0) * 100)}%`;
    badge.className = `verdict-badge ${confidenceClass(confidence.level)}`;

    const range = market.recommended_range || {};
    document.querySelector("#stat-range").textContent =
      `${money(range.min, unit)} – ${money(range.max, unit)}`;
    document.querySelector("#stat-median").textContent = money(market.median, unit);
    document.querySelector("#stat-percentiles").textContent =
      `${money(market.p25, unit)} / ${money(market.p75, unit)}`;
    document.querySelector("#stat-sample").textContent =
      `${sample.observations || 0} obs · ${sample.sources || 0} fontes`;
    document.querySelector("#stat-minmax").textContent =
      `${money(market.minimum, unit)} / ${money(market.maximum, unit)}`;
    document.querySelector("#stat-monthly").textContent = money(market.monthly_equivalent, "month");

    const warnings = data.warnings || [];
    const warningsPanel = document.querySelector("#warnings-panel");
    const warningsList = document.querySelector("#warnings-list");
    warningsList.innerHTML = "";
    if (warnings.length) {
      warningsPanel.hidden = false;
      warnings.forEach((warning) => {
        const li = document.createElement("li");
        li.textContent = warning;
        warningsList.appendChild(li);
      });
    } else {
      warningsPanel.hidden = true;
    }

    const sourcesList = document.querySelector("#sources-list");
    sourcesList.innerHTML = "";
    const sources = data.sources || [];
    if (!sources.length) {
      const empty = document.createElement("p");
      empty.className = "hint";
      empty.textContent = "Nenhuma fonte com observação válida.";
      sourcesList.appendChild(empty);
    } else {
      sources.forEach((source) => {
        const item = document.createElement("article");
        item.className = "list-item";
        item.innerHTML = `
          <strong>${escapeHtml(source.name || "fonte")}</strong>
          <span>${source.observations || 0} observação(ões)</span>
          <a href="${escapeAttr(source.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(source.url)}</a>
        `;
        sourcesList.appendChild(item);
      });
    }

    const observations = data.observations || [];
    document.querySelector("#observations-count").textContent =
      `${observations.length} registro(s)`;
    const tbody = document.querySelector("#observations-body");
    tbody.innerHTML = "";
    if (!observations.length) {
      const row = document.createElement("tr");
      row.innerHTML = `<td colspan="6">Nenhuma observação com evidência salarial.</td>`;
      tbody.appendChild(row);
      return;
    }

    observations.forEach((obs) => {
      const normalized = obs.normalized_salary || {};
      const row = document.createElement("tr");
      if (obs.excluded_from_statistics) row.classList.add("row-excluded");
      const location = [obs.location?.city, obs.location?.state].filter(Boolean).join("/");
      row.innerHTML = `
        <td>
          <strong>${escapeHtml(obs.role || obs.normalized_role || "—")}</strong>
          <div class="cell-meta">${escapeHtml([obs.seniority, location].filter(Boolean).join(" · "))}</div>
        </td>
        <td>${escapeHtml(obs.employment_type || "—")}</td>
        <td>${escapeHtml(observedLabel(obs))}</td>
        <td>${escapeHtml(money(normalized.value, normalized.unit || unit))}</td>
        <td>
          <a href="${escapeAttr(obs.source_url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(obs.source || "fonte")}</a>
          <div class="cell-meta">${escapeHtml(obs.evidence_type || "")}${obs.excluded_from_statistics ? " · outlier" : ""}</div>
        </td>
        <td><div class="evidence-cell">${escapeHtml(obs.evidence || "")}</div></td>
      `;
      tbody.appendChild(row);
    });
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }

  function escapeAttr(value) {
    return escapeHtml(value).replaceAll("'", "&#39;");
  }

  function checkedValues(name) {
    return Array.from(form.querySelectorAll(`input[name="${name}"]:checked`)).map((el) => el.value);
  }

  function buildPayload() {
    const skills = String(form.skills.value || "")
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
    const sourceJobId = (form.source_job_id?.value || "").trim();
    return {
      profile: form.profile.value.trim(),
      skills,
      seniority: form.seniority.value,
      allocation_model: form.allocation_model.value,
      location: {
        city: form.city.value.trim(),
        state: form.state.value.trim().toUpperCase(),
        country: form.country.value.trim().toUpperCase() || "BR",
      },
      target_contract: form.target_contract.value,
      providers: {
        search_engines: checkedValues("search_engines"),
        crawlers: checkedValues("crawlers"),
      },
      force_refresh: form.force_refresh.checked,
      source_job_id: sourceJobId || null,
    };
  }

  function applyPrefill(prefill) {
    if (!prefill) return;
    form.profile.value = prefill.profile || "";
    form.skills.value = Array.isArray(prefill.skills) ? prefill.skills.join(", ") : "";
    if (prefill.seniority) form.seniority.value = prefill.seniority;
    if (prefill.allocation_model) form.allocation_model.value = prefill.allocation_model;
    if (prefill.target_contract) form.target_contract.value = prefill.target_contract;
    form.city.value = prefill.location?.city || "";
    form.state.value = prefill.location?.state || "";
    form.country.value = prefill.location?.country || "BR";
    if (form.source_job_id) form.source_job_id.value = prefill.source_job_id || "";
  }

  const jobSelect = document.querySelector("#job-source-select");
  jobSelect?.addEventListener("change", async () => {
    const jobId = jobSelect.value;
    showError("");
    if (!jobId) {
      if (form.source_job_id) form.source_job_id.value = "";
      const url = new URL(window.location.href);
      url.searchParams.delete("job_id");
      window.history.replaceState({}, "", url);
      return;
    }
    try {
      showOverlay("Carregando dados da vaga…", 20, "Carregando");
      const response = await fetch(`/api/v1/compensation/prefill/${encodeURIComponent(jobId)}`, {
        credentials: "same-origin",
      });
      if (!response.ok) throw new Error("Não foi possível carregar a vaga selecionada.");
      const prefill = await response.json();
      applyPrefill(prefill);
      const url = new URL(window.location.href);
      url.searchParams.set("job_id", jobId);
      window.history.replaceState({}, "", url);
    } catch (error) {
      showError(error.message || "Erro ao pré-preencher a vaga.");
    } finally {
      hideOverlay();
    }
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    showError("");
    const payload = buildPayload();
    if (!payload.profile) {
      showError("Informe o perfil/cargo.");
      return;
    }

    submitBtn.disabled = true;
    showOverlay("Enfileirando pesquisa de mercado…", 1, "Na fila");

    try {
      const response = await fetch("/api/v1/compensation/research/async", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        credentials: "same-origin",
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        let detail = "Falha ao iniciar pesquisa de remuneração.";
        try {
          const err = await response.json();
          if (typeof err.detail === "string") detail = err.detail;
          else if (Array.isArray(err.detail)) detail = err.detail.map((item) => item.msg || item).join("; ");
        } catch {
          /* ignore */
        }
        throw new Error(detail);
      }
      const task = await response.json();
      if (!task.task_id) throw new Error("Resposta inválida do servidor.");
      showOverlay(task.message || "Pesquisa iniciada…", task.progress || 2, "Em andamento");
      const data = await pollResearchTask(task.task_id);
      renderResults(data);
      await refreshHistory(data.research_id);
      resultsEl.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (error) {
      showError(error.message || "Erro inesperado.");
    } finally {
      hideOverlay();
      submitBtn.disabled = false;
    }
  });

  clearBtn?.addEventListener("click", () => {
    resultsEl.hidden = true;
    clearBtn.hidden = true;
    showError("");
    setActiveHistory("");
  });

  historyList?.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-cache-key]");
    if (!button) return;
    const cacheKey = button.getAttribute("data-cache-key");
    if (!cacheKey) return;
    showError("");
    submitBtn.disabled = true;
    showOverlay("Carregando pesquisa do cache…", 30, "Carregando");
    try {
      const response = await fetch(`/api/v1/compensation/history/${encodeURIComponent(cacheKey)}`, {
        credentials: "same-origin",
      });
      if (!response.ok) throw new Error("Não foi possível abrir a pesquisa do cache.");
      setProgress(90);
      const data = await response.json();
      activeCacheKey = cacheKey;
      setActiveHistory(cacheKey);
      const url = new URL(window.location.href);
      url.searchParams.set("cache_key", cacheKey);
      window.history.replaceState({}, "", url);
      renderResults(data);
      setProgress(100);
      resultsEl.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (error) {
      showError(error.message || "Erro ao carregar histórico.");
    } finally {
      hideOverlay();
      submitBtn.disabled = false;
    }
  });

  function confidenceBadgeClass(level) {
    return confidenceClass(level);
  }

  function formatHistoryDate(value) {
    if (!value) return "—";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return date.toLocaleString("pt-BR");
  }

  function setActiveHistory(cacheKey) {
    activeCacheKey = cacheKey || "";
    historyList?.querySelectorAll(".history-item").forEach((item) => {
      item.classList.toggle("is-active", item.getAttribute("data-cache-key") === activeCacheKey);
    });
  }

  function renderHistory(items, preferredResearchId) {
    if (!historyList) return;
    if (historyCount) historyCount.textContent = `${items.length} registro(s)`;
    if (!items.length) {
      historyList.innerHTML = `<p class="hint" id="history-empty">Nenhuma pesquisa em cache ainda.</p>`;
      return;
    }
    if (preferredResearchId) {
      const match = items.find((item) => item.research_id === preferredResearchId);
      if (match) activeCacheKey = match.cache_key;
    }
    historyList.innerHTML = items
      .map((item) => {
        const median =
          item.median == null
            ? ""
            : ` · mediana ${money(item.median, item.unit || "hour")}`;
        const search = (item.search_engines_used || []).join(", ") || "nenhum";
        return `
          <button type="button"
            class="list-item history-item ${item.cache_key === activeCacheKey ? "is-active" : ""}"
            data-cache-key="${escapeAttr(item.cache_key)}">
            <div class="history-item-top">
              <strong>${escapeHtml(item.normalized_role || "Sem cargo normalizado")}</strong>
              <span class="verdict-badge ${confidenceBadgeClass(item.confidence_level)}">${escapeHtml(item.confidence_level || "LOW")}</span>
            </div>
            <span>
              ${escapeHtml(item.contract_type || "—")}
              · ${item.observations || 0} obs
              · ${item.sources || 0} fontes
              ${median}
            </span>
            <span class="cell-meta">
              ${escapeHtml(formatHistoryDate(item.created_at))}
              · cache ${escapeHtml(String(item.cache_key || "").slice(0, 12))}…
              · search ${escapeHtml(search)}
            </span>
          </button>
        `;
      })
      .join("");
  }

  async function refreshHistory(preferredResearchId) {
    try {
      const response = await fetch("/api/v1/compensation/history", { credentials: "same-origin" });
      if (!response.ok) return;
      const payload = await response.json();
      renderHistory(payload.items || [], preferredResearchId);
      if (activeCacheKey) {
        const url = new URL(window.location.href);
        url.searchParams.set("cache_key", activeCacheKey);
        window.history.replaceState({}, "", url);
      }
    } catch {
      /* ignore history refresh failures */
    }
  }

  const lastDataEl = document.querySelector("#last-research-data");
  if (lastDataEl?.textContent?.trim()) {
    try {
      renderResults(JSON.parse(lastDataEl.textContent));
    } catch {
      /* ignore invalid cache bootstrap */
    }
  }
})();
