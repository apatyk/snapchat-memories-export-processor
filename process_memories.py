# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "pillow",
#     "loguru",
#     "tqdm",
#     "ffmpeg-python",
# ]
# ///

import argparse
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Dict, List, Optional

import ffmpeg
from loguru import logger
from PIL import Image, UnidentifiedImageError
from tqdm import tqdm

# Directories
OUTPUT_DIR = Path("output")
BASE_DIR = Path("base")


class MemoryPair:
    """Represents a base file and its optional overlay."""

    def __init__(self, base_path: Path, overlay_path: Optional[Path] = None):
        self.base_path = base_path
        self.overlay_path = overlay_path
        self.is_video = base_path.suffix.lower() in [".mp4", ".mov"]

    def __repr__(self):
        return f"MemoryPair({self.base_path.name}, overlay={self.overlay_path.name if self.overlay_path else None})"


def init_argparser() -> argparse.Namespace:
    """Parse command line arguments for source path."""

    def valid_path(path_str):
        path = Path(path_str)
        if not path.exists():
            raise argparse.ArgumentTypeError(f"Path does not exist '{path_str}'")
        return path

    parser = argparse.ArgumentParser(prog="process_memories")
    parser.add_argument(
        "path", type=valid_path, help="path to Snapchat memories directory"
    )
    args = parser.parse_args()

    return args


def scan_memories(memories_dir: Path) -> List[MemoryPair]:
    """Scan the memories directory and pair base files with overlays."""

    if not memories_dir.exists():
        logger.error(f"{memories_dir} directory not found")
        sys.exit(1)

    # Process each sub-directory and group files by their identifier (date_uuid)
    files_by_id: Dict[str, Dict[str, Path]] = {}
    for file_path in memories_dir.iterdir():
        if not file_path.is_dir():
            # Copy files that don't need any processing to output directory
            shutil.copy2(file_path, memories_dir / OUTPUT_DIR / file_path.name)
            continue
        for subdir_path in file_path.iterdir():
            # Parse filename: UUID-TYPE.ext
            match = re.match(r"(.+?)-(main|overlay)\.(\w+)$", subdir_path.name)
            if not match:
                continue

            identifier, file_type, _ = match.groups()

            if identifier not in files_by_id:
                files_by_id[identifier] = {}

            files_by_id[identifier][file_type] = subdir_path

    # Create MemoryPair objects
    pairs = []
    for identifier, files in sorted(files_by_id.items()):
        if "main" in files:
            overlay = files.get("overlay")
            pairs.append(MemoryPair(files["main"], overlay))

    return pairs


def combine_image(base_path: Path, overlay_path: Path, output_path: Path):
    """Combine base image with overlay using PIL."""

    base = Image.open(base_path)
    try:
        overlay = Image.open(overlay_path).convert("RGBA")
    except UnidentifiedImageError:
        logger.warning(
            f"Overlay '{overlay_path}' not found, copying base image with no overlay"
        )
        shutil.copy2(base_path, output_path)
        return

    # Preserve EXIF data from base image
    exif = base.info.get("exif")

    # Resize overlay to match base if needed
    if base.size != overlay.size:
        overlay = overlay.resize(base.size, Image.Resampling.LANCZOS)

    # Convert base to RGBA for compositing
    if base.mode != "RGBA":
        base = base.convert("RGBA")

    # Composite the images
    combined = Image.alpha_composite(base, overlay)

    # Convert back to RGB for JPEG output
    if output_path.suffix.lower() in [".jpg", ".jpeg"]:
        combined = combined.convert("RGB")

    # Save with EXIF data if available
    if exif:
        combined.save(output_path, quality=95, exif=exif)
    else:
        combined.save(output_path, quality=95)

    # Copy file timestamps from original
    stat = os.stat(base_path)
    os.utime(output_path, (stat.st_atime, stat.st_mtime))


def combine_video(base_path: Path, overlay_path: Path, output_path: Path):
    """Combine base video with overlay using ffmpeg."""

    input_video = ffmpeg.input(str(base_path))
    input_overlay = ffmpeg.input(str(overlay_path))

    # Get video info to scale overlay to match
    probe = ffmpeg.probe(str(base_path))
    video_info = next(s for s in probe["streams"] if s["codec_type"] == "video")
    width = int(video_info["width"])
    height = int(video_info["height"])

    # Scale overlay to match video dimensions, then overlay at 0,0
    scaled_overlay = ffmpeg.filter(input_overlay, "scale", height, width)
    video_output = ffmpeg.filter([input_video, scaled_overlay], "overlay", x="0", y="0")
    audio_output = input_video.audio

    # Combine video and audio streams, preserving metadata
    output = ffmpeg.output(
        video_output,
        audio_output,
        str(output_path),
        vcodec="libx264",
        acodec="copy",
        pix_fmt="yuv420p",
        **{"map_metadata": 0},
    )

    # Run ffmpeg
    ffmpeg.run(output, overwrite_output=True, quiet=True)

    # Copy file timestamps from original
    stat = os.stat(base_path)
    os.utime(output_path, (stat.st_atime, stat.st_mtime))


def main(source_dir):
    output_path = source_dir / OUTPUT_DIR
    base_path = source_dir / BASE_DIR

    # Create output directories
    output_path.mkdir(exist_ok=True)
    base_path.mkdir(exist_ok=True)

    # Scan for memory pairs
    logger.info("Scanning memories directory...")
    pairs = scan_memories(source_dir)
    logger.info(f"Found {len(pairs)} memory files\n")

    # Process all pairs
    for pair in tqdm(pairs):
        # Copy base to bases directory (copy2 preserves timestamps)
        base_copy = base_path / pair.base_path.name
        shutil.copy2(pair.base_path, base_copy)

        # Combine with overlay if present
        if pair.overlay_path:
            combined_name = pair.base_path.name.replace("-main", "-combined")
            combined_path = output_path / combined_name

            if pair.is_video:
                combine_video(pair.base_path, pair.overlay_path, combined_path)
            else:
                combine_image(pair.base_path, pair.overlay_path, combined_path)

    logger.success("Processing complete!")


if __name__ == "__main__":
    args = init_argparser()
    main(args.path)
