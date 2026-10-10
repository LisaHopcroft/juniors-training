import gspread
import pandas as pd
from gspread.utils import rowcol_to_a1
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.ticker import FuncFormatter
from datetime import datetime
import configparser

from src.juniors_utils import to_seconds, to_mmss

output_dir = "img/"

now = datetime.now()
now_readable = now.strftime("%Y-%m-%d")
now_string = now.strftime("%y%m%d")
bench_name = "BENCH 500m"
bench_string = bench_name.replace(" ", "_")

config = configparser.ConfigParser()
config.optionxform = str  # keep the key's capitalisation (the default lowercases keys)
config.read("config.ini")

sheet_id = config["sheets"][bench_name]

gc = gspread.service_account(filename="service_account.json")
sh = gc.open_by_key(sheet_id)  # the long string in the sheet's URL

meta = sh.fetch_sheet_metadata({"fields": "sheets(properties(sheetId,title),tables)"})

df = None
for sheet in meta["sheets"]:
    for t in sheet.get("tables", []):
        if t["name"] == bench_name:
            r = t["range"]
            # API indices are 0-based and the end is exclusive; A1 is 1-based and inclusive
            start = rowcol_to_a1(
                r.get("startRowIndex", 0) + 1, r.get("startColumnIndex", 0) + 1
            )
            end = rowcol_to_a1(r["endRowIndex"], r["endColumnIndex"])

            ws = sh.worksheet(sheet["properties"]["title"])
            values = ws.get(f"{start}:{end}")

            df = pd.DataFrame(
                values[1:], columns=values[0]
            )  # first row is the table header
            break

print(df if df is not None else "Table not found")

# Work on individual intervals only (no Total rows)
intervals = df[df["Interval"].astype(str) != "Total"].copy()
intervals["Split secs"] = intervals["Split decimal"].apply(to_seconds)

summary = intervals.groupby("Junior")["Split secs"].agg(
    mean_split="mean", best_split="min"
)

# Human-readable version
summary["mean_split (mm:ss)"] = summary["mean_split"].apply(to_mmss)
summary["best_split (mm:ss)"] = summary["best_split"].apply(to_mmss)

print(summary)

intervals = df[df["Interval"].astype(str) != "Total"].copy()
intervals["Split secs"] = intervals["Split decimal"].apply(to_seconds)
intervals["Interval"] = pd.to_numeric(intervals["Interval"], errors="coerce")
intervals["Date"] = pd.to_datetime(intervals["Date"], format="%d/%m/%Y")

# Same colour scale for every junior, so colours mean the same thing on every plot
vmin, vmax = intervals["Interval"].min(), intervals["Interval"].max()

for junior, data in intervals.groupby("Junior"):
    fig, ax = plt.subplots(figsize=(8, 5))

    # Points coloured by interval number
    sc = ax.scatter(
        data["Date"],
        data["Split secs"],
        c=data["Interval"],
        cmap="viridis",
        vmin=vmin,
        vmax=vmax,
        s=60,
        alpha=0.9,
        edgecolor="white",
        linewidth=0.5,
        zorder=3,
    )
    cbar = fig.colorbar(sc, ax=ax, label="Interval")
    cbar.set_ticks(sorted(data["Interval"].dropna().unique()))

    # Session mean line across dates
    summary_by_date = (
        data.groupby("Date")["Split secs"]
		.agg(mean="mean", best="min")
        .sort_index()
	)

    ax.plot(
        summary_by_date.index,
        summary_by_date["mean"],
        color="black",
        marker="D",
        markersize=6,
        linewidth=1.5,
        alpha=0.7,
        label="Session mean",
        zorder=2,
    )

    # Label each session mean with its date, mean and best split
    for date, row in summary_by_date.iterrows():
        ax.annotate(
            f"{date:%d %b %Y}\nMean {to_mmss(row['mean'])}\nBest {to_mmss(row['best'])}",
            xy=(date, row["mean"]),
			xytext=(-15, 0),  # offset in points; adjust to taste
			textcoords="offset points",
			ha="right",
			fontsize=8,
			bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="grey", alpha=0.8),
			zorder=4,
        )

    ax.plot(
        summary_by_date.index,
        # summary_by_date["best"],
        summary_by_date["best"].cummin(),
        color="crimson",
        marker="o",
        markersize=12,
        markerfacecolor="none",  # hollow ring, so the interval colour shows through
        markeredgecolor="crimson",
        markeredgewidth=1.5,
        linewidth=1.5,
        linestyle="--",
        alpha=0.8,
        label="Season best",
        zorder=4,
    )

    ax.set_title(f"{junior}: {bench_name} ({now_readable})")
    ax.set_xlabel("Date", fontweight="bold")
    ax.set_ylabel("Split (min:sec per 500m)", fontweight="bold")
    ax.set_xlim(pd.Timestamp("2026-09-01"), pd.Timestamp("2027-07-01"))

    # y values as m:ss
    ax.yaxis.set_major_formatter(FuncFormatter(lambda x, _: to_mmss(x)))

    # Tidy date axis
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m/%y"))
    fig.autofmt_xdate()

    ax.grid(alpha=0.3)
    ax.legend(loc="best")
    fig.tight_layout()
    fig.savefig(f"{output_dir}/{now_string}_{junior}_{bench_string}.png", dpi=150)
