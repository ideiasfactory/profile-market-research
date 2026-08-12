(() => {
  const dataNode = document.querySelector("#score-chart-data");
  const canvas = document.querySelector("#score-chart");
  if (!dataNode || !canvas || typeof Chart === "undefined") return;

  let chartData;
  try {
    chartData = JSON.parse(dataNode.textContent || "{}");
  } catch {
    return;
  }

  const expectedColor = "rgba(56, 189, 248, 0.85)";
  const expectedFill = "rgba(56, 189, 248, 0.12)";
  const candidateColor = "rgba(34, 197, 94, 0.9)";
  const candidateFill = "rgba(34, 197, 94, 0.18)";
  const gridColor = "rgba(152, 166, 186, 0.25)";
  const tickColor = "#98a6ba";

  let activeView = "radar-category";
  let chart;

  function datasetPair(expected, candidate) {
    return [
      {
        label: "Esperado",
        data: expected,
        borderColor: expectedColor,
        backgroundColor: expectedFill,
        pointBackgroundColor: expectedColor,
        pointBorderColor: "#0b1222",
        borderWidth: 2,
      },
      {
        label: "Candidato",
        data: candidate,
        borderColor: candidateColor,
        backgroundColor: candidateFill,
        pointBackgroundColor: candidateColor,
        pointBorderColor: "#0b1222",
        borderWidth: 2,
      },
    ];
  }

  function configForView(view) {
    if (view === "bars") {
      const source = chartData.category || { labels: [], expected: [], candidate: [], max: 100 };
      return {
        type: "bar",
        data: {
          labels: source.labels,
          datasets: [
            {
              label: "Esperado",
              data: source.expected,
              backgroundColor: expectedColor,
              borderRadius: 8,
              maxBarThickness: 42,
            },
            {
              label: "Candidato",
              data: source.candidate,
              backgroundColor: candidateColor,
              borderRadius: 8,
              maxBarThickness: 42,
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: {
              labels: { color: tickColor },
            },
            tooltip: {
              callbacks: {
                label(context) {
                  return `${context.dataset.label}: ${context.parsed.y}%`;
                },
              },
            },
          },
          scales: {
            x: {
              ticks: { color: tickColor },
              grid: { color: gridColor },
            },
            y: {
              min: 0,
              max: 100,
              ticks: {
                color: tickColor,
                callback(value) {
                  return `${value}%`;
                },
              },
              grid: { color: gridColor },
            },
          },
        },
      };
    }

    const source =
      view === "radar-skills"
        ? chartData.skills || { labels: [], expected: [], candidate: [], max: 5 }
        : chartData.category || { labels: [], expected: [], candidate: [], max: 100 };
    const maxValue = Number(source.max) || 100;
    const unit = source.unit || "";

    return {
      type: "radar",
      data: {
        labels: source.labels,
        datasets: datasetPair(source.expected, source.candidate),
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            labels: { color: tickColor },
          },
          tooltip: {
            callbacks: {
              label(context) {
                const value = context.parsed.r;
                const suffix = unit === "%" ? "%" : unit === "nota" ? "/5" : "";
                return `${context.dataset.label}: ${value}${suffix}`;
              },
            },
          },
        },
        scales: {
          r: {
            min: 0,
            max: maxValue,
            ticks: {
              color: tickColor,
              backdropColor: "transparent",
              stepSize: maxValue <= 5 ? 1 : 20,
              callback(value) {
                return unit === "%" ? `${value}%` : value;
              },
            },
            grid: { color: gridColor },
            angleLines: { color: gridColor },
            pointLabels: {
              color: "#e5edf8",
              font: { size: 12, weight: "600" },
            },
          },
        },
        elements: {
          line: { tension: 0.15 },
        },
      },
    };
  }

  function render(view) {
    activeView = view;
    const config = configForView(view);
    if (chart) chart.destroy();
    chart = new Chart(canvas.getContext("2d"), config);
  }

  document.querySelectorAll("[data-chart-view]").forEach((button) => {
    button.addEventListener("click", () => {
      const view = button.dataset.chartView;
      document.querySelectorAll("[data-chart-view]").forEach((btn) => {
        const active = btn === button;
        btn.classList.toggle("is-active", active);
        btn.setAttribute("aria-selected", active ? "true" : "false");
      });
      render(view);
    });
  });

  render(activeView);
})();
