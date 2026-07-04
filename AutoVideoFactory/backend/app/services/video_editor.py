from __future__ import annotations

import asyncio
import json
import math
import os
import random
import shutil
import subprocess
from pathlib import Path
from typing import Any, Optional

from ..core.exceptions import VideoProcessingError
from ..core.logging import get_logger

logger = get_logger("autovideofactory.services.editor")


def _find_ffmpeg() -> str:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        return "ffmpeg"
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        return "ffmpeg"


class VideoEditorService:
    def __init__(self) -> None:
        self._output_dir = Path("output/videos")
        self._output_dir.mkdir(parents=True, exist_ok=True)

    def _generate_ken_burns_clip(
        self,
        image_path: str,
        output_path: str,
        direction: str = "in",
        duration: float = 5.0,
        width: int = 1080,
        height: int = 1920,
    ) -> bool:
        try:
            from PIL import Image
            import numpy as np
        except ImportError:
            logger.warning("PIL/numpy not installed, falling back to static clip")
            return False

        try:
            img = Image.open(image_path).convert("RGB")
        except Exception as e:
            logger.warning(f"Failed to open image for Ken Burns: {e}")
            return False

        fps = 20
        n_frames = int(duration * fps)
        zoom_start = 1.0
        zoom_end = 1.3
        if direction == "out":
            zoom_start, zoom_end = zoom_end, zoom_start

        # Scale image to fill target, crop to center
        ratio = max(width / img.width, height / img.height)
        new_w = int(img.width * ratio)
        new_h = int(img.height * ratio)
        img_resized = img.resize((new_w, new_h), Image.LANCZOS)
        left = (new_w - width) // 2
        top_ = (new_h - height) // 2
        base_np = np.array(img_resized.crop((left, top_, left + width, top_ + height)), dtype=np.uint8)

        zoom_step = (zoom_end - zoom_start) / max(n_frames - 1, 1)
        ffmpeg = _find_ffmpeg()
        cmd = [
            ffmpeg, "-y",
            "-f", "rawvideo",
            "-vcodec", "rawvideo",
            "-s", f"{width}x{height}",
            "-pix_fmt", "rgb24",
            "-r", str(fps),
            "-i", "-",
            "-c:v", "libx264", "-preset", "fast",
            "-pix_fmt", "yuv420p",
            "-frames:v", str(n_frames),
            output_path,
        ]

        try:
            proc = subprocess.Popen(
                cmd, stdin=subprocess.PIPE,
                stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            )
            for n in range(n_frames):
                zoom = zoom_start + zoom_step * n
                crop_w = max(int(width / zoom), 1)
                crop_h = max(int(height / zoom), 1)
                cx = (width - crop_w) // 2
                cy = (height - crop_h) // 2
                frame_np = base_np[cy:cy + crop_h, cx:cx + crop_w]
                frame = Image.fromarray(frame_np).resize((width, height), Image.BILINEAR)
                proc.stdin.write(frame.tobytes())
            proc.stdin.close()
            proc.wait(timeout=120)
            ok = proc.returncode == 0 and Path(output_path).stat().st_size > 0
            if not ok:
                logger.warning(f"Ken Burns FFmpeg encoding failed (rc={proc.returncode})")
            return ok
        except Exception as e:
            logger.warning(f"Ken Burns frame generation failed: {e}")
            return False

    async def compose(
        self,
        clips: list[dict[str, Any]],
        background_music: Optional[str] = None,
        voiceover_path: Optional[str] = None,
        subtitle_path: Optional[str] = None,
        ken_burns: bool = True,
        output_width: int = 1080,
        output_height: int = 1920,
        output_path: Optional[str] = None,
    ) -> str:
        output_path = output_path or str(self._output_dir / f"final_{abs(hash(str(clips)))}.mp4")

        if not clips:
            raise VideoProcessingError("No clips provided for composition")

        if len(clips) == 1:
            clip = clips[0]
            input_path = clip.get("file_path", "")
            duration = clip.get("duration", 5)
            if not os.path.exists(input_path):
                logger.warning(f"Clip not found: {input_path}, creating placeholder")
                input_path = await self._create_placeholder(output_width, output_height, duration)

            is_image = input_path.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))

            if is_image and ken_burns:
                seed = random.randint(0, 1)
                direction = "out" if seed else "in"
                temp_ken = str(self._output_dir / f"single_ken_{abs(hash(str(clips)))}.mp4")
                ok = await asyncio.to_thread(
                    self._generate_ken_burns_clip,
                    input_path, temp_ken, direction, duration,
                    output_width, output_height,
                )
                if ok:
                    input_path = temp_ken
                    # Now use the Ken Burns clip as a regular video input
                    ffmpeg = _find_ffmpeg()
                    cmd = [ffmpeg, "-y", "-i", input_path,
                           "-c:v", "copy"]
                else:
                    ffmpeg = _find_ffmpeg()
                    cmd = [ffmpeg, "-y", "-i", input_path]
            else:
                cmd += ["-i", input_path,
                        "-vf", f"scale={output_width}:{output_height}:force_original_aspect_ratio=decrease,pad={output_width}:{output_height}:(ow-iw)/2:(oh-ih)/2",
                        "-c:v", "libx264", "-preset", "medium", "-crf", "23"]

            if voiceover_path and os.path.exists(voiceover_path):
                cmd += ["-i", voiceover_path,
                        "-c:a", "aac", "-b:a", "128k",
                        "-map", "0:v:0", "-map", "1:a:0", "-shortest"]
            elif background_music and os.path.exists(background_music):
                cmd += ["-i", background_music,
                        "-c:a", "aac", "-b:a", "128k",
                        "-map", "0:v:0", "-map", "1:a:0",
                        "-filter_complex", f"[1:a]volume={clip.get('music_volume', 0.3)}[a1]",
                        "-map", "[a1]", "-shortest"]

            cmd.append(output_path)

            try:
                subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=300)
                logger.info(f"Video composed: {output_path}")
                return output_path
            except subprocess.CalledProcessError as e:
                raise VideoProcessingError(f"FFmpeg composition failed: {e.stderr}") from e
            except FileNotFoundError:
                logger.warning("FFmpeg not found, creating placeholder output")
                Path(output_path).write_bytes(b"")
                return output_path

        temp_clips = []
        for i, clip in enumerate(clips):
            path = clip.get("file_path", "")
            if os.path.exists(path):
                dur = clip.get("duration", 5)
                temp_path = str(self._output_dir / f"temp_clip_{i}_{abs(hash(str(clips)))}.mp4")
                ffmpeg = _find_ffmpeg()

                if ken_burns:
                    direction = "out" if i % 2 else "in"
                    ok = await asyncio.to_thread(
                        self._generate_ken_burns_clip,
                        path, temp_path, direction, dur,
                        output_width, output_height,
                    )
                    if ok:
                        temp_clips.append(temp_path)
                        continue
                cmd = [
                    ffmpeg, "-y",
                    "-loop", "1",
                    "-i", path,
                    "-c:v", "libx264",
                    "-preset", "fast",
                    "-pix_fmt", "yuv420p",
                    "-vf", f"scale={output_width}:{output_height}:force_original_aspect_ratio=decrease,pad={output_width}:{output_height}:(ow-iw)/2:(oh-ih)/2",
                    "-t", str(dur),
                    "-r", "30",
                    temp_path,
                ]
                try:
                    subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=60)
                    temp_clips.append(temp_path)
                except Exception:
                    pass

        if not temp_clips:
            Path(output_path).write_bytes(b"")
            return output_path

        concat_output = str(self._output_dir / f"concat_raw_{abs(hash(str(clips)))}.mp4")
        if len(temp_clips) == 1:
            os.replace(temp_clips[0], concat_output)
        else:
            input_args = []
            for t in temp_clips:
                input_args.extend(["-i", t])
            cmd = [_find_ffmpeg(), "-y"] + input_args + [
                "-filter_complex",
                f"{''.join(f'[{i}:v]' for i in range(len(temp_clips)))}concat=n={len(temp_clips)}:v=1:a=0[vo]",
                "-map", "[vo]",
                "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                concat_output,
            ]
            try:
                subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=300)
            except Exception:
                Path(output_path).write_bytes(b"")
                return output_path

        if voiceover_path and os.path.exists(voiceover_path):
            audio_output = output_path
            cmd = [
                _find_ffmpeg(), "-y",
                "-i", concat_output,
                "-i", voiceover_path,
                "-c:v", "copy",
                "-c:a", "aac",
                "-b:a", "128k",
                "-map", "0:v:0",
                "-map", "1:a:0",
                "-shortest",
                audio_output,
            ]
            try:
                subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=300)
                logger.info(f"Video composed with voiceover: {audio_output}")
            except (subprocess.CalledProcessError, FileNotFoundError) as e:
                logger.warning(f"Voiceover overlay failed: {e}, returning video without audio")
                Path(output_path).write_bytes(b"")
                return output_path
        else:
            if os.path.exists(concat_output):
                os.replace(concat_output, output_path)

        if background_music and os.path.exists(background_music) and os.path.exists(output_path):
            mixed_path = await self.add_background_music(output_path, background_music)
            if mixed_path != output_path:
                os.replace(mixed_path, output_path)

        for t in temp_clips:
            try:
                os.remove(t)
            except Exception:
                pass

        return output_path

    async def add_subtitles(self, video_path: str, subtitle_path: str, burn_in: bool = True) -> str:
        if not os.path.exists(video_path):
            raise VideoProcessingError(f"Video not found: {video_path}")
        output_path = video_path.replace(".mp4", "_subtitled.mp4")

        if burn_in and os.path.exists(subtitle_path):
            cmd = [
                _find_ffmpeg(), "-y",
                "-i", video_path,
                "-vf", f"subtitles={subtitle_path}",
                "-c:a", "copy",
                output_path,
            ]
            try:
                subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=300)
                return output_path
            except (subprocess.CalledProcessError, FileNotFoundError):
                return video_path
        return video_path

    async def add_background_music(self, video_path: str, music_path: str, volume: float = 0.3) -> str:
        if not os.path.exists(video_path) or not os.path.exists(music_path):
            return video_path
        output_path = video_path.replace(".mp4", "_music.mp4")
        ffmpeg = _find_ffmpeg()

        has_audio = self._has_audio_stream(video_path)
        if has_audio:
            cmd = [
                ffmpeg, "-y",
                "-i", video_path,
                "-i", music_path,
                "-filter_complex", f"[1:a]volume={volume}[a1];[0:a][a1]amix=inputs=2:duration=first[a]",
                "-map", "0:v",
                "-map", "[a]",
                "-c:v", "copy",
                output_path,
            ]
        else:
            cmd = [
                ffmpeg, "-y",
                "-i", video_path,
                "-i", music_path,
                "-map", "0:v",
                "-map", "1:a",
                "-c:v", "copy",
                "-c:a", "aac", "-b:a", "64k",
                "-shortest",
                output_path,
            ]

        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=300)
            return output_path
        except (subprocess.CalledProcessError, FileNotFoundError):
            return video_path

    @staticmethod
    def _has_audio_stream(video_path: str) -> bool:
        try:
            result = subprocess.run(
                [_find_ffmpeg(), "-i", video_path],
                capture_output=True, text=True, timeout=30,
            )
            return "Audio:" in result.stderr
        except Exception:
            return True

    async def resize(self, video_path: str, width: int, height: int) -> str:
        if not os.path.exists(video_path):
            return video_path
        output_path = video_path.replace(".mp4", f"_{width}x{height}.mp4")
        cmd = [_find_ffmpeg(), "-y", "-i", video_path, "-vf", f"scale={width}:{height}", output_path]
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=300)
            return output_path
        except (subprocess.CalledProcessError, FileNotFoundError):
            return video_path

    async def trim(self, video_path: str, start: float, end: float) -> str:
        if not os.path.exists(video_path):
            return video_path
        output_path = video_path.replace(".mp4", "_trimmed.mp4")
        cmd = [_find_ffmpeg(), "-y", "-i", video_path, "-ss", str(start), "-to", str(end), "-c", "copy", output_path]
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=300)
            return output_path
        except (subprocess.CalledProcessError, FileNotFoundError):
            return video_path

    async def extract_thumbnail(self, video_path: str, timestamp: Optional[float] = None) -> str:
        if not os.path.exists(video_path):
            raise VideoProcessingError(f"Video not found: {video_path}")
        output_path = video_path.replace(".mp4", "_thumb.jpg")
        ts = timestamp or 1.0
        cmd = [_find_ffmpeg(), "-y", "-i", video_path, "-ss", str(ts), "-vframes", "1", "-q:v", "2", output_path]
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=60)
            return output_path
        except (subprocess.CalledProcessError, FileNotFoundError):
            return ""

    async def _create_placeholder(self, width: int, height: int, duration: float) -> str:
        path = str(self._output_dir / f"placeholder_{width}x{height}_{duration}s.mp4")
        import random
        colors = ["0x1a1a2e", "0x16213e", "0x0f3460", "0x533483", "0x2d4059", "0x1b1b2f"]
        c = random.choice(colors)
        cmd = [
            _find_ffmpeg(), "-y",
            "-f", "lavfi",
            "-i", f"color=c={c}:s={width}x{height}:d={duration}:r=30",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-pix_fmt", "yuv420p",
            path,
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=30)
        except (subprocess.CalledProcessError, FileNotFoundError):
            Path(path).write_bytes(b"")
        return path
