# FFmpeg build input

The Windows executables `ffmpeg.exe` and `ffprobe.exe` are deliberately not
tracked in the source repository. They exceed GitHub's regular file-size limit
and are third-party release-build inputs rather than YiF source code.

To build a Windows installer, place the two executables in this `bin/` folder.
Use the reviewed LGPL build documented in `../../THIRD_PARTY_NOTICES.md` and
`../../LICENSE_REVIEW.md`. The build script checks that both files are present
before it packages an installer.

Public YiF release assets include the executables together with the applicable
LGPL license and notice files.

