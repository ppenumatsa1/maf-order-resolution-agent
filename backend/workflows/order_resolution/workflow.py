from __future__ import annotations

import sys

from app.maf.workflows import order_resolution as _order_resolution

sys.modules[__name__] = _order_resolution
