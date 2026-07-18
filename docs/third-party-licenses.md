# Third-party license inventory

This is an inventory, not legal advice or a statement that redistribution review is complete. A release must be blocked if a dependency's redistribution terms have not been reviewed for the exact bundled version.

| Dependency | Project | Installed-version command | License identifier | Redistribution note | Bundled |
| --- | --- | --- | --- | --- | --- |
| Python | https://www.python.org/ | `.venv/bin/python --version` | PSF-2.0 | Include notices required by the Python distribution. | Yes, through PyInstaller runtime |
| PySide6 / Qt | https://doc.qt.io/qtforpython-6/ | `.venv/bin/python -c 'import PySide6; print(PySide6.__version__)'` | LGPL-3.0-only / GPL-3.0-only | Verify LGPL dynamic-linking and Qt notice obligations before distribution. | Yes |
| OpenCV | https://opencv.org/ | `.venv/bin/python -c 'import cv2; print(cv2.__version__)'` | Apache-2.0 | Preserve applicable notices. | Yes |
| Pydantic | https://docs.pydantic.dev/ | `.venv/bin/python -c 'import pydantic; print(pydantic.__version__)'` | MIT | Preserve license text/notice where required. | Yes |
| NumPy | https://numpy.org/ | `.venv/bin/python -c 'import numpy; print(numpy.__version__)'` | BSD-3-Clause | Preserve license text/notice where required. | Yes |
| Typer | https://typer.tiangolo.com/ | `.venv/bin/python -c 'import typer; print(typer.__version__)'` | MIT | CLI dependency; review if PyInstaller includes it. | Yes |
| FFmpeg | https://ffmpeg.org/ | `ffmpeg -version` | LGPL-2.1-or-later or GPL depending on build | Installed separately by the operator; inspect the actual Homebrew build configuration. | No |
| DeepFilterNet | https://github.com/Rikorose/DeepFilterNet | `.venv/bin/python -c 'import importlib.metadata as m; print(m.version("deepfilternet"))'` | Verify package metadata before release | Optional module; include only after reviewing its model/code licenses. | Optional |

Run these commands on the release environment and retain the resulting notices with the release artifacts. No row above constitutes legal approval.
