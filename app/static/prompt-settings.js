(() => {
  const root = document.getElementById("prompt-editor");
  const select = document.getElementById("prompt-version-select");
  const content = document.getElementById("prompt-content");
  if (!root || !select || !content) return;

  const promptId = root.dataset.promptId;
  select.addEventListener("change", async () => {
    const versionId = select.value;
    try {
      const response = await fetch(
        `/api/v1/settings/prompts/${encodeURIComponent(promptId)}?version_id=${encodeURIComponent(versionId)}`
      );
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Falha ao carregar versão");
      content.value = data.content || "";
    } catch (err) {
      alert(err.message || String(err));
    }
  });
})();
