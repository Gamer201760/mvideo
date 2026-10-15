import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
REPORT = json.loads((ROOT / "reports" / "final.json").read_text(encoding="utf-8"))
OUT = ROOT / "docs" / "images" / "results"
OUT.mkdir(parents=True, exist_ok=True)
plt.rcParams.update({"figure.dpi": 130, "axes.spines.top": False, "axes.spines.right": False})

STAGES = ["baseline", "ranker", "ranker+decision", "ranker+decision+twins", "fused"]
TITLES = ["Базлайн", "Ранжировщик", "+ Jev", "+ двойники", "Сборка"]
GROUPS = [("all", "Все"), ("split:new_category", "Новые категории"),
          ("category:smartphones", "Смартфоны"), ("category:laptops", "Ноутбуки")]
COLORS = ["#b8c4d6", "#8aa2c4", "#5b7fb3", "#3b6ea5", "#1f3f73"]

rows = {(r["stage"], r["group"]): r for r in REPORT["ablation"]}

fig, ax = plt.subplots(figsize=(9, 4))
width = 0.16
for i, (stage, title) in enumerate(zip(STAGES, TITLES, strict=True)):
    values = [rows.get((stage, g), {}).get("f1", 0) * 100 for g, _ in GROUPS]
    xs = [j + (i - 2) * width for j in range(len(GROUPS))]
    bars = ax.bar(xs, values, width=width, color=COLORS[i], label=title)
    for bar, value in zip(bars, values, strict=True):
        ax.text(bar.get_x() + bar.get_width() / 2, value + 0.6, f"{value:.0f}", ha="center",
                fontsize=7)
ax.set_xticks(range(len(GROUPS)), [t for _, t in GROUPS])
ax.set_ylabel("micro F1, %")
ax.set_ylim(0, 100)
ax.set_title("Абляция на test + новых категориях: что даёт каждый шаг")
ax.legend(ncol=5, fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.1), frameon=False)
fig.tight_layout()
fig.savefig(OUT / "ablation.png", bbox_inches="tight")

bins = [b for b in REPORT["reliability"] if b["count"]]
fig, ax = plt.subplots(figsize=(4.6, 4.2))
ax.plot([0, 1], [0, 1], color="#999999", linestyle="--", linewidth=1, label="идеал")
ax.plot([b["confidence"] for b in bins], [b["accuracy"] for b in bins], marker="o",
        color="#1f3f73", label="сборка")
ax.set_xlabel("уверенность")
ax.set_ylabel("доля верных значений")
ax.set_title(f"Калибровка итоговой уверенности, ECE = {REPORT['ece']:.3f}")
ax.legend(fontsize=8)
fig.tight_layout()
fig.savefig(OUT / "reliability.png", bbox_inches="tight")

curve = REPORT["val_curve"]
fig, ax = plt.subplots(figsize=(5.6, 3.8))
ax.plot([p["threshold"] for p in curve], [p["precision"] * 100 for p in curve], label="precision",
        color="#1f3f73")
ax.plot([p["threshold"] for p in curve], [p["recall"] * 100 for p in curve], label="recall",
        color="#5b7fb3")
ax.plot([p["threshold"] for p in curve], [p["coverage"] * 100 for p in curve],
        label="покрытие слотов", color="#b07a2a")
ax.axvline(REPORT["threshold"], color="#999999", linestyle="--", linewidth=1)
ax.set_xlabel("порог уверенности (val)")
ax.set_ylabel("%")
ax.set_title("Порог: точность против покрытия")
ax.legend(fontsize=8)
fig.tight_layout()
fig.savefig(OUT / "threshold.png", bbox_inches="tight")
print("charts:", sorted(p.name for p in OUT.glob("*.png")))
