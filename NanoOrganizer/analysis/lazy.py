#!/usr/bin/env python3
"""
Lazy frame access – read one frame at a time, or all of them, by asking.

Eager reading is right until it is not.  Forty spectra is a 100 kB array and
arguing about it wastes more time than reading it.  Four hundred micrographs
is 12 GB, and a notebook that reads them to show you the third one is a
notebook you restart.

:class:`LazyFrames` is the middle: it resolves the file list up front — so
``len()``, the paths and the per-frame metadata are available immediately —
and reads pixels only when a frame is actually indexed.

    frames = org.data("S01", "tem", lazy=True)
    len(frames)                 # no file opened
    frames[2]                   # one file opened
    for array, info in frames:  # one at a time, never all at once
        ...
    frames.load()               # all of them, as one array, having asked

It is a sequence, not a bare generator, on purpose: a generator cannot be
indexed, cannot report its length, and is empty the second time you use it —
all three of which a notebook will want within five minutes.

A single file holding a 3D volume is memory-mapped rather than read, so a
tomogram is sliceable without ever being resident.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple

import numpy as np

#: Suffixes numpy can memory-map directly.
MAPPABLE = {".npy"}


class LazyFrames(Sequence):
    """A measurement's frames, read on demand.

    Parameters
    ----------
    measurement, resolver
        What to read and how to find it.
    kind : {"curve", "image", "volume"}
        Which reader each frame goes through.  Taken from the measurement's
        group by :func:`frames_for`.

    Attributes
    ----------
    paths : list of Path
        The resolved files, in order.  Available without reading any of them.
    """

    def __init__(self, measurement, resolver, kind: str = "image"):
        self.measurement = measurement
        self.resolver = resolver
        self.kind = kind
        self.paths: List[Path] = list(measurement.resolve(resolver))
        self._planes: Optional[int] = None

        if not self.paths:
            raise FileNotFoundError(
                f"No files resolve for {measurement.measurement_id}")

        if kind == "volume" and len(self.paths) == 1:
            # One file holding a stack: the frames are its planes, and the
            # file is mapped rather than read so indexing one costs one plane.
            self._planes = self._map_volume().shape[0]

    # -- introspection ---------------------------------------------------

    def __len__(self) -> int:
        return self._planes if self._planes is not None else len(self.paths)

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        where = (f"{len(self.paths)} files" if self._planes is None
                 else f"{self._planes} planes of {self.paths[0].name}")
        return (f"<LazyFrames {self.measurement.measurement_id} "
                f"{self.kind}: {where}, unread>")

    @property
    def names(self) -> List[str]:
        """One label per frame, without opening anything."""
        if self._planes is not None:
            return [f"plane {i}" for i in range(self._planes)]
        return [p.name for p in self.paths]

    def table(self):
        """Per-frame metadata — index, file, and any time or temperature."""
        import pandas as pd

        from NanoOrganizer.analysis import frames as _frames

        if self._planes is not None:
            return pd.DataFrame({"index": range(self._planes),
                                 "file": self.paths[0].name,
                                 "plane": range(self._planes)})
        return pd.DataFrame(_frames.frame_table(self.measurement,
                                                self.resolver))

    # -- reading ---------------------------------------------------------

    def _map_volume(self) -> np.ndarray:
        path = self.paths[0]
        if path.suffix.lower() in MAPPABLE:
            return np.load(path, mmap_mode="r")
        from NanoOrganizer.analysis.reading import read_array

        return np.asarray(read_array(path))

    def __getitem__(self, index):
        if isinstance(index, slice):
            return [self[i] for i in range(*index.indices(len(self)))]

        count = len(self)
        if not -count <= index < count:
            raise IndexError(f"frame {index} of {count}")
        index = index % count

        from NanoOrganizer.analysis import reading

        if self._planes is not None:
            plane = np.asarray(self._map_volume()[index], dtype=float)
            return plane, {"file": self.paths[0].name, "plane": index,
                           "n_frames": self._planes, "shape": plane.shape}

        if self.kind == "curve":
            array = np.asarray(reading.read_array(self.paths[index]),
                               dtype=float)
            if array.ndim == 2 and array.shape[1] >= 2:
                x, y = array[:, 0], array[:, 1]
            else:
                x, y = np.arange(array.size, dtype=float), array.ravel()
            return x, y, {"file": self.paths[index].name, "index": index,
                          "n_frames": len(self.paths)}

        return reading.load_image(self.measurement, self.resolver, index)

    def __iter__(self) -> Iterator:
        for index in range(len(self)):
            yield self[index]

    # -- giving in -------------------------------------------------------

    def load(self, max_frames: Optional[int] = None):
        """Read every frame into one array — the eager answer, asked for.

        Returns what ``data(..., lazy=False)`` returns for this group:
        ``(x, Y, info)`` for curves, ``(array, info)`` for a volume or a
        single image.
        """
        count = len(self) if max_frames is None else min(len(self), max_frames)

        if self.kind == "curve":
            axis = None
            rows = []
            labels = []
            for index in range(count):
                x, y, info = self[index]
                if axis is None:
                    axis = x
                elif len(y) != len(axis):
                    raise ValueError(
                        f"{info['file']} has {len(y)} points but the first "
                        f"frame has {len(axis)}; these are not one series")
                rows.append(y)
                labels.append(info["file"])
            return axis, np.vstack(rows), {"labels": labels,
                                           "source": f"{count} files"}

        if self.kind == "volume" and self._planes is not None:
            return (np.asarray(self._map_volume()[:count], dtype=float),
                    {"source": f"{count} planes of {self.paths[0].name}",
                     "n_frames": count})

        # Images and multi-file volumes alike: ``load`` means *all of them*.
        # One frame comes back as the plain 2D array, because a (1, h, w)
        # stack is a shape you would only ever index away again.
        frames = [self[index][0] for index in range(count)]
        info = {"n_frames": count,
                "files": [p.name for p in self.paths[:count]]}
        if count == 1:
            info["source"] = self.paths[0].name
            return frames[0], info

        shapes = {f.shape for f in frames}
        if len(shapes) != 1:
            raise ValueError(
                f"{self.measurement.measurement_id}: frames have "
                f"{len(shapes)} different shapes, so they cannot be stacked. "
                f"Index them one at a time instead.")
        info["source"] = f"stacked {count} frames"
        return np.stack(frames), info


def frames_for(measurement, resolver) -> LazyFrames:
    """A :class:`LazyFrames` with the reader its group implies."""
    group = measurement.group
    kind = "curve" if group in ("curve", "correlation") else group
    return LazyFrames(measurement, resolver, kind=kind)


__all__ = ["LazyFrames", "frames_for", "MAPPABLE"]
