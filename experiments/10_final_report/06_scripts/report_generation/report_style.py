"""Shared matplotlib style for every 10_final_report/ figure: large, legible
fonts and a consistent dpi, applied via rcParams so all figures in this
report look like one system regardless of which build script drew them."""
import matplotlib

BIG_STYLE = {
    "figure.dpi": 170,
    "savefig.dpi": 170,
    "font.size": 13,
    "axes.titlesize": 15,
    "axes.titleweight": "bold",
    "axes.labelsize": 13,
    "xtick.labelsize": 12,
    "ytick.labelsize": 12,
    "legend.fontsize": 12,
    "figure.titlesize": 16,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.alpha": 0.25,
}


def apply():
    matplotlib.rcParams.update(BIG_STYLE)


COLOR_VAE = "#0072B2"
COLOR_DENSE = "#D55E00"
COLOR_BENIGN = "#0072B2"
COLOR_APACHE_BENCH = "#D55E00"
COLOR_PORTSCAN = "#009E73"
COLOR_SLOWLORIS = "#CC79A7"
COLOR_TYPE = {"apache_bench": COLOR_APACHE_BENCH, "portscan": COLOR_PORTSCAN, "slowloris": COLOR_SLOWLORIS}
