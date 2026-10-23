"""Summarise and plot junior training results held in Google Sheets tables."""

import configparser
import os
from datetime import datetime

import gspread
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd
from gspread.utils import rowcol_to_a1
from matplotlib.ticker import FuncFormatter

from src.juniors_utils import to_mmss, to_seconds

HIGH_RES_COLUMNS = [
    "junior",
    "date",
    "measurement",
    "split decimal",
    "spm",
    "time decimal",
    "format",
    "notes",
]


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
OUTPUT_DIR = "img/"
CONFIG_FILE = "config.ini"
CREDENTIALS_FILE = "service_account.json"
X_LIMITS = (pd.Timestamp("2026-09-01"), pd.Timestamp("2027-07-01"))


# ---------------------------------------------------------------------------
# Loading data
# ---------------------------------------------------------------------------
def get_sheet_id(config_file=CONFIG_FILE):
    """Look up the spreadsheet ID for a test in the config file."""
    config = configparser.ConfigParser()
    config.optionxform = str  # keep key capitalisation (default lowercases keys)
    config.read(config_file)
    return config["sheets"]["id"]


def fetch_table(test_name):
    """Return the Google Sheets table called `test_name` as a DataFrame."""
    gc = gspread.service_account(filename=CREDENTIALS_FILE)
    sh = gc.open_by_key(get_sheet_id())

    meta = sh.fetch_sheet_metadata(
        {"fields": "sheets(properties(sheetId,title),tables)"}
    )

    for sheet in meta["sheets"]:
        for table in sheet.get("tables", []):
            if table["name"] != test_name:
                continue

            r = table["range"]
            # API indices are 0-based and the end is exclusive;
            # A1 notation is 1-based and inclusive
            start = rowcol_to_a1(
                r.get("startRowIndex", 0) + 1, r.get("startColumnIndex", 0) + 1
            )
            end = rowcol_to_a1(r["endRowIndex"], r["endColumnIndex"])

            ws = sh.worksheet(sheet["properties"]["title"])
            values = ws.get(f"{start}:{end}")
            return pd.DataFrame(values[1:], columns=values[0])  # first row = header

    raise ValueError(f"Table '{test_name}' not found in the spreadsheet")


# ---------------------------------------------------------------------------
# Preparing data
# ---------------------------------------------------------------------------
def prepare_intervals(df):
    """Keep individual intervals only (no Total rows) and convert column types."""
    intervals = df[df["interval"].astype(str) != "Total"].copy()
    intervals["split secs"] = intervals["split decimal"].apply(to_seconds)
    intervals["interval"] = pd.to_numeric(intervals["interval"], errors="coerce")
    intervals["date"] = pd.to_datetime(intervals["date"], format="%d/%m/%Y")
    return intervals


def extract_high_resolution_data(df):
    """Pick out the high-resolution columns and convert their types.

    Like prepare_intervals(), but for tables with one row per measurement
    rather than per interval. Columns not in HIGH_RES_COLUMNS are ignored.
    Adds 'split secs' and 'time secs' (numeric seconds) alongside the originals.
    """
    missing = [c for c in HIGH_RES_COLUMNS if c not in df.columns]
    if missing:
        raise KeyError(f"Missing expected columns: {missing}")

    data = df[HIGH_RES_COLUMNS].copy()

    # Drop any Total rows, as prepare_intervals() does
    data = data[data["measurement"].astype(str) != "Total"].copy()

    data["date"] = pd.to_datetime(data["date"], format="%d/%m/%Y")
    data["measurement"] = pd.to_numeric(data["measurement"], errors="coerce")
    data["split secs"] = data["split decimal"].apply(to_seconds)
    data["spm"] = pd.to_numeric(data["spm"], errors="coerce")
    data["time secs"] = data["time decimal"].apply(to_seconds)

    # Keep a sensible column order: originals first, converted values beside them
    return data[
        [
            "junior",
            "date",
            "measurement",
            "split decimal",
            "split secs",
            "spm",
            "time decimal",
            "time secs",
            "format",
            "notes",
        ]
    ]

def summarise_by_junior(intervals):
    """Mean and best split per junior, in seconds and mm:ss."""
    summary = intervals.groupby("junior")["split secs"].agg(
        mean_split="mean", best_split="min"
    )
    summary["mean_split (mm:ss)"] = summary["mean_split"].apply(to_mmss)
    summary["best_split (mm:ss)"] = summary["best_split"].apply(to_mmss)
    return summary


# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------
def plot_intervals_per_junior(junior, data, test_name, vmin, vmax, date_stamp, file_stamp):
    """Draw and save the 'repeated intervals over time' graph for one junior."""
    fig, ax = plt.subplots(figsize=(8, 5))

    # Points coloured by interval number
    sc = ax.scatter(
        data["date"],
        data["split secs"],
        c=data["interval"],
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
    cbar.set_ticks(sorted(data["interval"].dropna().unique()))

    # Mean and best split for each session date
    by_date = (
        data.groupby("date")["split secs"].agg(mean="mean", best="min").sort_index()
    )

    # Session mean line across dates
    ax.plot(
        by_date.index,
        by_date["mean"],
        color="black",
        marker="D",
        markersize=6,
        linewidth=1.5,
        alpha=0.7,
        label="Session mean",
        zorder=2,
    )

    # Label each session mean with its date, mean and best split
    for date, row in by_date.iterrows():
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

    # Season best: running fastest split, so it only ever improves
    ax.plot(
        by_date.index,
        by_date["best"].cummin(),
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

    ax.set_title(f"{junior}: {test_name} ({date_stamp})")
    ax.set_xlabel("Date", fontweight="bold")
    ax.set_ylabel("Split (min:sec per 500m)", fontweight="bold")
    ax.set_xlim(*X_LIMITS)

    # y values as m:ss
    ax.yaxis.set_major_formatter(FuncFormatter(lambda x, _: to_mmss(x)))

    # Tidy date axis
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m/%y"))
    fig.autofmt_xdate()

    ax.grid(alpha=0.3)
    ax.legend(loc="best")
    fig.tight_layout()

    filename = f"{file_stamp}_{junior}_{test_name.replace(' ', '_')}.png"
    fig.savefig(os.path.join(OUTPUT_DIR, filename), dpi=150)
    plt.close(fig)


def plot_segments_per_junior(
    junior, data, test_name, vmin, vmax, date_stamp, file_stamp
):
    """Draw and save the 'segments' graph for one junior.

    x axis: measurement (100, 200, 300 ...); y axis: split.
    One line per session date (coloured earliest to latest), with each date's
    mean and best split in the legend, plus the mean and best split at each
    measurement across all sessions.
    """
    fig, ax = plt.subplots(figsize=(10, 5))

    cmap = plt.get_cmap("viridis")
    n_dates = data["date"].nunique()

    ### --------------------------------------------------------- ###
    ### PLOT 1: One line per session date
    ### --------------------------------------------------------- ###
    for i, (date, session) in enumerate(data.groupby("date")):
        session = session.sort_values("measurement")
        colour = cmap(i / (n_dates - 1) if n_dates > 1 else 0.5)
        mean_split = session["split secs"].mean()
        best_split = session["split secs"].min()
        ax.plot(
            session["measurement"],
            session["split secs"],
            marker="o",
            markersize=5,
            linewidth=1.2,
            color=colour,
            alpha=0.85,
            label=(
                f"{date:%d %b %Y} "
                f"(mean {to_mmss(mean_split)}, best {to_mmss(best_split)})"
            ),
            zorder=3,
        )

    # Mean and best split at each measurement, across all sessions
    by_measurement = (
        data.groupby("measurement")["split secs"]
        .agg(mean="mean", best="min")
        .sort_index()
    )

    ax.plot(
        by_measurement.index,
        by_measurement["mean"],
        color="black",
        marker="D",
        markersize=6,
        linewidth=2,
        alpha=0.7,
        label="Mean (all sessions)",
        zorder=4,
    )

    ax.set_title(f"{junior}: {test_name} ({date_stamp})")
    ax.set_xlabel("Measurement", fontweight="bold")
    ax.set_ylabel("Split (min:sec per 500m)", fontweight="bold")
    ax.set_xticks(sorted(data["measurement"].dropna().unique()))

    # y values as m:ss
    ax.yaxis.set_major_formatter(FuncFormatter(lambda x, _: to_mmss(x)))

    ax.grid(alpha=0.3)
    ax.legend(loc="center left", bbox_to_anchor=(1.02, 0.5), fontsize=8)
    fig.tight_layout()

    filename = f"{file_stamp}_{junior}_{test_name.replace(' ', '_')}_segments.png"
    fig.savefig(os.path.join(OUTPUT_DIR, filename), dpi=150, bbox_inches="tight")
    plt.close(fig)

    ### --------------------------------------------------------- ###
    ### PLOT 2: Boxplot per date
    ### --------------------------------------------------------- ###

    fig, ax = plt.subplots(figsize=(8, 5))

    # Points coloured by interval number
    sc = ax.scatter(
        data["date"],
        data["split secs"],
        c=data["measurement"],
        cmap="viridis",
        vmin=vmin,
        vmax=vmax,
        s=60,
        alpha=0.9,
        edgecolor="white",
        linewidth=0.5,
        zorder=3,
    )
    cbar = fig.colorbar(sc, ax=ax, label="Segment")
    cbar.set_ticks(sorted(data["measurement"].dropna().unique()))

    # Mean and best split for each session date
    by_date = (
        data.groupby("date")["split secs"].agg(mean="mean", best="min").sort_index()
    )

    # Session mean line across dates
    ax.plot(
        by_date.index,
        by_date["mean"],
        color="black",
        marker="D",
        markersize=6,
        linewidth=1.5,
        alpha=0.7,
        label="Session mean",
        zorder=2,
    )

    # Label each session mean with its date, mean and best split
    for date, row in by_date.iterrows():
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

    # Season best: running fastest split, so it only ever improves
    ax.plot(
        by_date.index,
        by_date["best"].cummin(),
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

    ax.set_title(f"{junior}: {test_name} ({date_stamp})")
    ax.set_xlabel("Date", fontweight="bold")
    ax.set_ylabel("Split (min:sec per 500m)", fontweight="bold")
    # ax.set_xlim(*X_LIMITS)

    # y values as m:ss
    ax.yaxis.set_major_formatter(FuncFormatter(lambda x, _: to_mmss(x)))

    # Tidy date axis
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m/%y"))
    fig.autofmt_xdate()

    ax.grid(alpha=0.3)
    ax.legend(loc="best")
    fig.tight_layout()

    filename = f"{file_stamp}_{junior}_{test_name.replace(' ', '_')}_summary-over-time.png"
    fig.savefig(os.path.join(OUTPUT_DIR, filename), dpi=150)
    plt.close(fig)


def repeated_intervals_over_time(test_name):
    """Plot 'repeated intervals over time' for every junior on a given test.

    `test_name` is the name of the table in the Google Sheet and the key in
    config.ini (e.g. "BENCH 500m"). One PNG per junior is saved in OUTPUT_DIR.
    """
    now = datetime.now()
    date_stamp = now.strftime("%Y-%m-%d")
    file_stamp = now.strftime("%y%m%d")

    df = fetch_table(test_name)
    print(df)

    intervals = prepare_intervals(df)
    print(summarise_by_junior(intervals))

    # Same colour scale for every junior, so colours mean the same on every plot
    vmin, vmax = intervals["interval"].min(), intervals["interval"].max()

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    for junior, data in intervals.groupby("junior"):
        plot_intervals_per_junior(junior, data, test_name, vmin, vmax, date_stamp, file_stamp)


def high_resolution_plots(test_name):
    """Plot high resolution data (i.e., one interval, broken into segments),
    summarised over time for every junior on a given test.

    `test_name` is the name of the table in the Google Sheet and the key in
    config.ini (e.g. "BENCH 1k"). One PNG per junior is saved in OUTPUT_DIR.
    """
    now = datetime.now()
    date_stamp = now.strftime("%Y-%m-%d")
    file_stamp = now.strftime("%y%m%d")

    df = fetch_table(test_name)
    print(df)

    segments = extract_high_resolution_data(df)

    print(segments)

    print(summarise_by_junior(segments))

    # Same colour scale for every junior, so colours mean the same on every plot
    vmin, vmax = segments["measurement"].min(), segments["measurement"].max()

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    for junior, data in segments.groupby("junior"):
        plot_segments_per_junior(junior, data, test_name, vmin, vmax, date_stamp, file_stamp)


if __name__ == "__main__":
    # repeated_intervals_over_time("BENCH 500m")
    high_resolution_plots("BENCH 1k")
