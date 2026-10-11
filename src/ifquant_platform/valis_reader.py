"""Explicit bounded PNG reader for the isolated VALIS runtime.

Uses VALIS's reader extension point. It avoids Bio-Formats/JVM discovery for
already decoded, byte-bound PNG planes and carries declared physical units.
"""
import numpy as np
from PIL import Image
from valis import slide_io

from .imaging import require


class CalibratedPNGReader(slide_io.ImageReader):
    def __init__(self, src_f, pixel_size_um_xy, **kwargs):
        self.pixel_size_um_xy = pixel_size_um_xy
        super().__init__(src_f, **kwargs)

    def create_metadata(self):
        meta = slide_io.MetaData('IFQuant bounded PNG', slide_io.IMG_RDR)
        with Image.open(self.src_f) as image:
            require(image.format == 'PNG' and image.mode == 'RGB' and image.width*image.height <= 16_000_000,
                    'VALIS bridge requires bounded RGB PNG planes')
            meta.slide_dimensions = np.array([[image.width, image.height]])
        meta.is_rgb, meta.n_channels = True, 3
        meta.pixel_physical_size_xyu = (*self.pixel_size_um_xy, 'µm')
        meta.bf_datatype = 'uint8'
        return meta
