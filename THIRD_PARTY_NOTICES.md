# Third-party notices

Last updated: 18 August 2026. This file documents the external components used
to build Years in Focus 0.1.4. It does not replace a complete legal review for
public or commercial distribution.

## Python components

The application is packaged with Python and PyInstaller. The reviewed build
environment includes, in particular, the following runtime components:

| Component | reviewed version | license / note |
| --- | --- | --- |
| Python | 3.11 (build environment) | PSF License |
| Pillow | 12.3.0 | HPND |
| NumPy | 2.4.6 | BSD-3-Clause; license text included in the package |
| OpenCV / opencv-contrib-python | 5.0.0.93 | Apache-2.0; license text included in the package |
| MediaPipe | 0.10.35 | Apache-2.0; license text included in the package |
| PyMySQL | 1.2.0 | MIT; bundled for optional MariaDB digiKam import |
| PyInstaller | 6.21.0 | GPL-2.0-or-later with bootloader exception |

Further indirect Python dependencies are bundled by PyInstaller as required.
The portable output includes the license texts supplied with those packages,
where available.

## Models

| File | SHA-256 | origin / licensing note |
| --- | --- | --- |
| `models/mediapipe/face_landmarker.task` | `64184E229B263107BC2B804C6625DB1341FF2BB731874B0BCC2FE6544E0BC9FF` | Google AI Edge Face Landmarker / Face Mesh V2; Apache-2.0 according to the model card |
| `models/yunet/face_detection_yunet_2023mar.onnx` | `8F2383E4DD3CFBB4553EA8718107FC0423210DC964F9F4280604804ED2552FA4` | OpenCV Zoo YuNet; MIT License, Copyright (c) 2020 Shiqi Yu. Source: https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet |

## FFmpeg

- Build: `N-126086-ge5ecfe8970-20260812`, Windows x64, LGPL variant.
- Provider: BtbN/FFmpeg-Builds.
- Build reference: `ffmpeg-win64-lgpl.zip`
- SHA-256 of the reviewed build reference:
  `AD8310426EF419E2ACCABBE57CC7B9970A1B976F6515AE1BB00ECC5CE31D73F2`
- Source revision: `e5ecfe8970`; source:
  <https://github.com/FFmpeg/FFmpeg/tree/e5ecfe8970>
- The release contains `ffmpeg.exe`, `ffprobe.exe`, the LGPLv3 license and
  `FFMPEG-NOTICE.txt` in `licenses/`.

Before every public release, availability of the matching FFmpeg source must be
checked again against the revision and build reference.

## Project license

YiF's own source code is released under the MIT License. This license does not
automatically apply to the third-party components listed above; their notices
and licenses must be observed separately.
