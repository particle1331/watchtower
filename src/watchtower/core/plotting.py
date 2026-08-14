"""High-level matplotlib plotting API for ML notebooks (ported into watchtower)."""

from __future__ import annotations

from typing import Any, cast

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.axes import Axes

__all__ = ["Plot", "Panel", "set_format"]

_ArrayLike = Any  # lists, numpy arrays, torch tensors


# ---------------------------------------------------------------------------
# Notebook setup
# ---------------------------------------------------------------------------

def set_format(fmt: str = "svg") -> None:
    """Set the inline figure format for Jupyter notebooks.

    Call once at the top of a notebook::

        from notebooks.plot import Plot, set_format
        set_format("svg")   # or "png", "retina"

    This is a thin wrapper around
    ``matplotlib_inline.backend_inline.set_matplotlib_formats``.
    """
    from matplotlib_inline import backend_inline
    backend_inline.set_matplotlib_formats(fmt)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _to_numpy(data: _ArrayLike) -> np.ndarray:
    """Convert lists, torch tensors, or arrays to numpy.

    Handles the common ``.detach().cpu().numpy()`` chain for torch tensors
    so callers never need to think about it.
    """
    if hasattr(data, "detach"):  # torch tensor
        return data.detach().cpu().numpy()
    return np.asarray(data)


def _apply_style(ax: Axes) -> None:
    """Apply default style to a single axes: remove top/right spines, dotted grid."""
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(linestyle="dotted", alpha=0.4)


def _ema(data: np.ndarray, span: int) -> np.ndarray:
    """Exponential moving average with the given span.

    Uses the same convention as pandas/TensorBoard: ``alpha = 2 / (span + 1)``.
    No lag — the output has the same length as the input and starts from
    the first data point.
    """
    alpha = 2.0 / (span + 1)
    out = np.empty_like(data, dtype=np.float64)
    out[0] = data[0]
    for i in range(1, len(data)):
        out[i] = alpha * data[i] + (1 - alpha) * out[i - 1]
    return out


_ANNOTATION_LOCS: dict[str, tuple[float, float, str, str]] = {
    "upper left":  (0.05, 0.95, "top", "left"),
    "upper right": (0.95, 0.95, "top", "right"),
    "lower left":  (0.05, 0.05, "bottom", "left"),
    "lower right": (0.95, 0.05, "bottom", "right"),
}


# ---------------------------------------------------------------------------
# Panel — wraps a single Axes
# ---------------------------------------------------------------------------

class Panel:
    """Chainable wrapper around a single ``matplotlib.axes.Axes``.

    Every drawing method returns ``self`` so calls can be chained::

        panel.line(y, label="train").line(y2, label="valid").labels(x="step")

    Access the underlying axes via ``panel.ax`` for anything not covered here.
    """

    def __init__(self, ax: Axes) -> None:
        self.ax = ax
        # Accumulate scatter data lazily for regression_line / diagonal_line
        self._scatter_chunks_x: list[np.ndarray] = []
        self._scatter_chunks_y: list[np.ndarray] = []

    def _get_scatter_data(self) -> tuple[np.ndarray, np.ndarray]:
        """Concatenate accumulated scatter chunks."""
        if not self._scatter_chunks_x:
            raise ValueError("No scatter data to use. Call .scatter() first.")
        x = np.concatenate(self._scatter_chunks_x)
        y = np.concatenate(self._scatter_chunks_y)
        return x, y

    # -- Line plot ----------------------------------------------------------

    def line(
        self,
        y: _ArrayLike,
        x: _ArrayLike | None = None,
        *,
        color: str | None = None,
        label: str | None = None,
        lw: float = 1.5,
        alpha: float = 1.0,
        smooth: int | None = None,
    ) -> Panel:
        """Line plot with optional exponential moving average smoothing.

        Parameters
        ----------
        y : array-like
            Y-axis values.
        x : array-like, optional
            X-axis values.  Defaults to ``range(len(y))``.
        smooth : int, optional
            If set, draws the raw trace at ``alpha=0.3`` and overlays an exponential 
            moving average (EMA) with based on smooth parameter at full opacity. Uses 
            ``ema_alpha = 2 / (smooth + 1)``(same convention as pandas and TensorBoard).  
            No lag — the smoothed line covers the full x range.
        """
        y = _to_numpy(y)
        x = np.arange(len(y)) if x is None else _to_numpy(x)

        if smooth is not None and smooth > 1:
            # Raw trace — faded
            self.ax.plot(x, y, color=color, lw=lw * 0.6, alpha=0.3)
            # Smoothed overlay — same length, no offset
            y_smooth = _ema(y, smooth)
            self.ax.plot(
                x, y_smooth,
                color=color, lw=lw, alpha=alpha, label=label,
            )
        else:
            self.ax.plot(x, y, color=color, lw=lw, alpha=alpha, label=label)
        return self

    # -- Scatter ------------------------------------------------------------

    def scatter(
        self,
        x: _ArrayLike,
        y: _ArrayLike,
        *,
        color: str | None = None,
        label: str | None = None,
        s: float = 80,
        alpha: float = 0.85,
        edgecolor: str | None = None,
        c: _ArrayLike | None = None,
        cmap: str | None = None,
    ) -> Panel:
        """Scatter plot.

        Use ``color=`` for a fixed colour per call (categorical grouping).
        Use ``c=`` with ``cmap=`` for continuous colouring.
        Passing both ``color`` and ``c`` raises ``ValueError``.
        """
        if color is not None and c is not None:
            raise ValueError("Pass 'color' or 'c', not both.")

        x = _to_numpy(x)
        y = _to_numpy(y)
        c = _to_numpy(c)

        self.ax.scatter(
            x, y,
            s=s, alpha=alpha, color=color, c=c, cmap=cmap,
            edgecolors=edgecolor, label=label,
        )
        # Accumulate for regression_line / diagonal_line
        self._scatter_chunks_x.append(x)
        self._scatter_chunks_y.append(y)
        return self

    # -- Bar ----------------------------------------------------------------

    def bar(
        self,
        x: _ArrayLike,
        height: _ArrayLike,
        *,
        color: str | None = None,
        label: str | None = None,
        width: float = 0.8,
        alpha: float = 1.0,
    ) -> Panel:
        """Bar chart."""
        x = _to_numpy(x)
        height = _to_numpy(height)
        self.ax.bar(
            x, height, width=width, color=color, label=label, alpha=alpha,
        )
        return self

    # -- Histogram ----------------------------------------------------------

    def histogram(
        self,
        data: _ArrayLike,
        *,
        bins: int = 30,
        color: str | None = None,
        label: str | None = None,
        density: bool = False,
        alpha: float = 0.7,
    ) -> Panel:
        """Histogram."""
        data = _to_numpy(data).ravel()
        self.ax.hist(
            data, bins=bins, color=color, label=label,
            density=density, alpha=alpha,
        )
        return self

    # -- Heatmap ------------------------------------------------------------

    def heatmap(
        self,
        matrix: _ArrayLike,
        *,
        row_labels: list[str] | None = None,
        col_labels: list[str] | None = None,
        cmap: str = "Blues",
        annot: bool = False,
        fmt: str = ".2f",
        vmin: float | None = None,
        vmax: float | None = None,
        colorbar: bool = True,
    ) -> Panel:
        """Heatmap via ``imshow`` with optional text annotations.

        Parameters
        ----------
        matrix : 2D array-like
            The data to display.
        annot : bool
            If True, write the numeric value in each cell.
        fmt : str
            Format string for annotations (e.g. ``".2f"``, ``"d"``).
            Applied to all floating-point dtypes (including float32/float16).
        """
        matrix = _to_numpy(matrix)
        im = self.ax.imshow(
            matrix, cmap=cmap, aspect="auto", vmin=vmin, vmax=vmax,
        )

        if annot:
            is_float = np.issubdtype(matrix.dtype, np.floating)
            for i in range(matrix.shape[0]):
                for j in range(matrix.shape[1]):
                    val = matrix[i, j]
                    text = format(val, fmt) if is_float else str(val)
                    self.ax.text(
                        j, i, text, ha="center", va="center", color="black",
                        fontsize=8,
                    )

        if row_labels is not None:
            self.ax.set_yticks(range(len(row_labels)))
            self.ax.set_yticklabels(row_labels, fontsize=8)
        if col_labels is not None:
            self.ax.set_xticks(range(len(col_labels)))
            self.ax.set_xticklabels(col_labels, fontsize=8, rotation=45, ha="right")

        if colorbar:
            plt.colorbar(im, ax=self.ax, fraction=0.046, pad=0.04)

        # Disable grid for heatmaps — it conflicts with imshow
        self.ax.grid(False)
        return self

    # -- Image --------------------------------------------------------------

    def image(
        self,
        img: _ArrayLike,
        *,
        cmap: str = "gray",
        vmin: float | None = None,
        vmax: float | None = None,
    ) -> Panel:
        """Display a single image. Turns off axes.

        Accepts ``(H, W)`` grayscale or ``(H, W, 3)`` / ``(H, W, 4)``
        RGB/RGBA arrays.  PyTorch's ``(C, H, W)`` format must be
        transposed before passing (e.g. ``img.permute(1, 2, 0)``).
        """
        img = _to_numpy(img)
        self.ax.imshow(img, cmap=cmap, vmin=vmin, vmax=vmax)
        self.ax.axis("off")
        return self

    # -- Reference lines ----------------------------------------------------

    def regression_line(
        self,
        *,
        color: str = "gray",
        lw: float = 1.5,
        linestyle: str = "dashed",
    ) -> Panel:
        """Draw a linear regression line through the accumulated scatter data."""
        x, y = self._get_scatter_data()
        if np.std(x) == 0:
            raise ValueError("Cannot fit regression: all x values are identical.")
        m, b = np.polyfit(x, y, 1)
        x_line = np.linspace(x.min(), x.max(), 200)
        self.ax.plot(
            x_line, m * x_line + b,
            color=color, lw=lw, linestyle=linestyle, zorder=0,
        )
        return self

    def diagonal_line(
        self,
        *,
        color: str = "gray",
        lw: float = 1.5,
        linestyle: str = "dashed",
    ) -> Panel:
        """Draw a y=x diagonal reference line.

        Uses the intersection of the current x/y axis limits so the
        diagonal does not distort the existing view.
        """
        # Let matplotlib auto-scale first from existing data, then read limits
        self.ax.autoscale_view()
        xlim = self.ax.get_xlim()
        ylim = self.ax.get_ylim()
        lo = max(xlim[0], ylim[0])
        hi = min(xlim[1], ylim[1])
        self.ax.plot(
            [lo, hi], [lo, hi],
            color=color, lw=lw, linestyle=linestyle, zorder=0,
        )
        # Restore limits so the diagonal doesn't expand them
        self.ax.set_xlim(xlim)
        self.ax.set_ylim(ylim)
        return self

    def hline(
        self,
        y: float,
        *,
        color: str = "gray",
        lw: float = 0.8,
        linestyle: str = "dashed",
        label: str | None = None,
    ) -> Panel:
        """Horizontal reference line."""
        self.ax.axhline(y, color=color, lw=lw, linestyle=linestyle, label=label)
        return self

    def vline(
        self,
        x: float,
        *,
        color: str = "gray",
        lw: float = 0.8,
        linestyle: str = "dashed",
        label: str | None = None,
    ) -> Panel:
        """Vertical reference line."""
        self.ax.axvline(x, color=color, lw=lw, linestyle=linestyle, label=label)
        return self

    def fill_between(
        self,
        x: _ArrayLike,
        lower: _ArrayLike,
        upper: _ArrayLike,
        *,
        color: str | None = None,
        alpha: float = 0.3,
    ) -> Panel:
        """Filled region between lower and upper bounds."""
        x = _to_numpy(x)
        lower = _to_numpy(lower)
        upper = _to_numpy(upper)
        self.ax.fill_between(x, lower, upper, color=color, alpha=alpha)
        return self

    # -- Annotations --------------------------------------------------------

    def annotate(
        self, text: str, loc: str = "upper left", *, fontsize: int = 11,
    ) -> Panel:
        """Place a text annotation at one of four corner locations.

        Parameters
        ----------
        loc : str
            One of ``"upper left"``, ``"upper right"``,
            ``"lower left"``, ``"lower right"``.
        """
        if loc not in _ANNOTATION_LOCS:
            raise ValueError(
                f"loc must be one of {list(_ANNOTATION_LOCS)}, got {loc!r}"
            )
        x, y, va, ha = _ANNOTATION_LOCS[loc]
        self.ax.text(
            x, y, text,
            transform=self.ax.transAxes, fontsize=fontsize,
            va=va, ha=ha,
        )
        return self

    # -- Axis configuration -------------------------------------------------

    def labels(
        self, x: str | None = None, y: str | None = None, title: str | None = None,
    ) -> Panel:
        """Set axis labels and/or panel title."""
        if x is not None:
            self.ax.set_xlabel(x)
        if y is not None:
            self.ax.set_ylabel(y)
        if title is not None:
            self.ax.set_title(title)
        return self

    def xlim(self, lo: float, hi: float) -> Panel:
        """Set x-axis limits."""
        self.ax.set_xlim(lo, hi)
        return self

    def ylim(self, lo: float, hi: float) -> Panel:
        """Set y-axis limits."""
        self.ax.set_ylim(lo, hi)
        return self

    def log_scale(self, axis: str = "y") -> Panel:
        """Set log scale on the given axis (``"x"``, ``"y"``, or ``"both"``)."""
        if axis in ("y", "both"):
            self.ax.set_yscale("log")
        if axis in ("x", "both"):
            self.ax.set_xscale("log")
        return self


# ---------------------------------------------------------------------------
# Plot — wraps figure + axes grid
# ---------------------------------------------------------------------------

class Plot:
    """Builder for matplotlib figures with a clean default style.

    Parameters
    ----------
    rows, cols : int
        Grid dimensions.  Defaults to a single panel (1x1).
    figsize : tuple of float, optional
        Figure size in inches.  Defaults to ``(5*cols, 4*rows)`` capped
        at reasonable maximums.
    title : str, optional
        Figure-level super-title.

    Examples
    --------
    ::

        p = Plot(1, 2, figsize=(10, 4))
        p[0].scatter(x, y, color="C0", label="A")
        p[1].line(losses, smooth=50)
        p.legend(loc="below")
        p.show()
    """

    def __init__(
        self,
        rows: int = 1,
        cols: int = 1,
        *,
        figsize: tuple[float, float] | None = None,
        title: str | None = None,
    ) -> None:
        self.rows = rows
        self.cols = cols

        if figsize is None:
            w = min(5 * cols, 16)
            h = min(4 * rows, 12)
            figsize = (w, h)

        self.fig, self._axes = plt.subplots(rows, cols, figsize=figsize)

        # Normalize axes to a flat array
        if rows == 1 and cols == 1:
            self._axes_flat = [self._axes]
        else:
            self._axes_flat = list(np.asarray(self._axes).flat)

        # Apply default style to every panel
        for ax in self._axes_flat:
            _apply_style(ax)

        # Wrap each axes in a Panel
        self._panels = [Panel(ax) for ax in self._axes_flat]

        if title is not None:
            self.fig.suptitle(title, fontsize=14)

    def __getitem__(self, idx: int | tuple[int, int]) -> Panel:
        """Access a panel by flat index ``plot[i]`` or 2D index ``plot[i, j]``."""
        if isinstance(idx, tuple):
            r, c = idx
            flat = r * self.cols + c
            return self._panels[flat]
        return self._panels[idx]

    @property
    def axes(self) -> list[Axes]:
        """List of all underlying matplotlib axes (flat order)."""
        return self._axes_flat

    # -- Figure-level methods -----------------------------------------------

    def legend(
        self,
        loc: str = "best",
        *,
        shared: bool | None = None,
        ncol: int | None = None,
        fontsize: int = 9,
        frameon: bool = False,
    ) -> Plot:
        """Add a legend.

        Parameters
        ----------
        loc : str
            Any matplotlib legend location string, plus two special values:

            - ``"below"`` — shared legend centered below all panels
              (always shared, regardless of *shared* flag).
            - ``"outside"`` — legend placed to the right of panels.
              Shared by default; set ``shared=False`` for per-panel legends.

            All other values (``"best"``, ``"upper left"``, etc.) place
            per-panel legends using the standard matplotlib positions.
            Set ``shared=True`` to aggregate them into a single
            figure-level legend at that location instead.
        shared : bool, optional
            If ``True``, collect and de-duplicate labels across all panels
            into a single figure-level legend.  If ``False``, each panel
            gets its own legend.  Defaults to ``True`` for ``"below"``
            and ``"outside"``, ``False`` otherwise.
        frameon : bool
            If ``True``, draw a box around the legend.  Defaults to
            ``False`` for a clean look.
        """
        # Resolve shared default
        if shared is None:
            shared = loc in ("below", "outside")

        if shared:
            # Collect handles/labels from all panels (de-duplicate by label)
            handles: list = []
            labels: list[str] = []
            seen: set[str] = set()
            for panel in self._panels:
                h, panel_labels = panel.ax.get_legend_handles_labels()
                for hi, li in zip(h, panel_labels, strict=True):
                    if li not in seen:
                        handles.append(hi)
                        labels.append(li)
                        seen.add(li)
            if not labels:
                return self

            if loc == "below":
                if ncol is None:
                    ncol = len(labels)
                self.fig.legend(
                    handles, labels,
                    loc="lower center",
                    bbox_to_anchor=(0.5, -0.08),
                    ncol=ncol,
                    frameon=frameon,
                    fontsize=fontsize,
                )
            elif loc == "outside":
                self.fig.legend(
                    handles, labels,
                    loc="center left",
                    bbox_to_anchor=(1.0, 0.5),
                    ncol=ncol or 1,
                    frameon=frameon,
                    fontsize=fontsize,
                )
            else:
                # Shared legend at a standard matplotlib location
                self.fig.legend(
                    handles, labels,
                    loc=cast(Any, loc),
                    ncol=ncol or 1,
                    frameon=frameon,
                    fontsize=fontsize,
                )
        else:
            # Per-panel legends
            if loc == "outside":
                for panel in self._panels:
                    h, panel_labels = panel.ax.get_legend_handles_labels()
                    if panel_labels:
                        panel.ax.legend(
                            loc="center left",
                            bbox_to_anchor=(1.0, 0.5),
                            frameon=frameon,
                            fontsize=fontsize,
                        )
            else:
                for panel in self._panels:
                    h, panel_labels = panel.ax.get_legend_handles_labels()
                    if panel_labels:
                        panel.ax.legend(
                            loc=cast(Any, loc), frameon=frameon, fontsize=fontsize,
                        )
        return self

    def images(
        self,
        batch: _ArrayLike,
        *,
        cmap: str = "gray",
        vmin: float | None = None,
        vmax: float | None = None,
    ) -> Plot:
        """Fill the entire grid with images from a batch array/tensor.

        Parameters
        ----------
        batch : array-like
            Shape ``(N, H, W)`` or ``(N, H, W, C)``.  ``N`` must be
            >= ``rows * cols``.  PyTorch's ``(N, C, H, W)`` format
            must be permuted before passing.
        """
        batch = _to_numpy(batch)
        n_panels = self.rows * self.cols
        for i in range(n_panels):
            ax = self._axes_flat[i]
            ax.imshow(batch[i], cmap=cmap, vmin=vmin, vmax=vmax)
            ax.axis("off")
            ax.grid(False)
        return self

    def show(self) -> None:
        """Apply tight layout, display the figure, and close it to free memory."""
        self.fig.tight_layout()
        plt.show()
        plt.close(self.fig)

    def save(self, path: str, *, dpi: int = 150) -> None:
        """Save the figure to a file and close it to free memory."""
        self.fig.tight_layout()
        self.fig.savefig(path, dpi=dpi, bbox_inches="tight")
        plt.close(self.fig)
