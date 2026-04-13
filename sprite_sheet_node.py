from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image
from PIL.PngImagePlugin import PngInfo

try:
    import folder_paths  # type: ignore
except Exception:  # pragma: no cover - local testing fallback
    folder_paths = None

try:
    import torch
except Exception:  # pragma: no cover - ComfyUI runtime should provide torch
    torch = None


def _default_output_directory() -> Path:
    if folder_paths is not None:
        try:
            return Path(folder_paths.get_output_directory())  # type: ignore[attr-defined]
        except Exception:
            pass
    return Path.cwd() / "output"


def _parse_frame_names(raw: str, frame_count: int) -> list[str]:
    text = (raw or "").strip()
    if not text:
        return [f"frame_{index + 1:05d}" for index in range(frame_count)]

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = None

    if isinstance(parsed, list):
        names = [str(item).strip() for item in parsed if str(item).strip()]
    else:
        names = []
        for line in text.splitlines():
            for part in line.split(","):
                item = part.strip()
                if item:
                    names.append(item)

    if len(names) != frame_count:
        raise ValueError(f"frame_names_json 需要 {frame_count} 个名字，当前收到 {len(names)} 个")
    return names


def _normalize_image_batch(images: Any) -> Any:
    if hasattr(images, "shape") and len(images.shape) == 3:
        return images.unsqueeze(0)
    return images


def _normalize_mask_batch(masks: Any) -> Any:
    if masks is None:
        return None
    if hasattr(masks, "shape") and len(masks.shape) == 2:
        return masks.unsqueeze(0)
    return masks


def _tensor_image_to_rgba(image: Any, mask: Any | None) -> Image.Image:
    image_array = np.clip(255.0 * image.cpu().numpy(), 0, 255).astype(np.uint8)

    if image_array.ndim != 3:
        raise ValueError(f"images 输入必须是 HWC，当前 shape={image_array.shape}")

    if image_array.shape[2] == 1:
        image_array = np.repeat(image_array, 3, axis=2)

    if image_array.shape[2] >= 4:
        rgba_array = image_array[:, :, :4]
    else:
        alpha = np.full((image_array.shape[0], image_array.shape[1]), 255, dtype=np.uint8)
        if mask is not None:
            alpha = np.clip(255.0 * mask.cpu().numpy(), 0, 255).astype(np.uint8)
        rgba_array = np.dstack([image_array[:, :, :3], alpha])

    return Image.fromarray(rgba_array, mode="RGBA")


def _alignment_offset(container_size: int, content_size: int, align: str) -> int:
    remaining = max(container_size - content_size, 0)
    if align in {"left", "top"}:
        return 0
    if align in {"right", "bottom"}:
        return remaining
    return remaining // 2


def _background_rgba(background: str) -> tuple[int, int, int, int]:
    if background == "white":
        return (255, 255, 255, 255)
    if background == "black":
        return (0, 0, 0, 255)
    return (0, 0, 0, 0)


def _next_output_path(filename_prefix: str, output_dir: Path) -> tuple[Path, str]:
    prefix_path = Path(filename_prefix)
    subfolder = "" if str(prefix_path.parent) == "." else prefix_path.parent.as_posix()
    stem = prefix_path.name or "sprite_sheet"

    full_output_folder = output_dir / subfolder
    full_output_folder.mkdir(parents=True, exist_ok=True)

    counter = 1
    while True:
        filename = f"{stem}_{counter:05d}_.png"
        full_path = full_output_folder / filename
        if not full_path.exists():
            return full_path, subfolder
        counter += 1


def _build_sprite_sheet_rgba(
    images: Any,
    masks: Any | None,
    columns: int,
    cell_width: int,
    cell_height: int,
    padding: int,
    margin: int,
    horizontal_align: str,
    vertical_align: str,
    background: str,
    metadata_key: str,
    frame_names_json: str,
) -> tuple[Image.Image, dict[str, Any]]:
    image_batch = _normalize_image_batch(images)
    frame_count = int(image_batch.shape[0])
    if frame_count <= 0:
        raise ValueError("images 不能为空")

    mask_batch = _normalize_mask_batch(masks)
    if mask_batch is not None and int(mask_batch.shape[0]) not in {1, frame_count}:
        raise ValueError(f"masks 批次大小需要是 1 或 {frame_count}，当前是 {int(mask_batch.shape[0])}")

    pil_frames: list[Image.Image] = []
    for index in range(frame_count):
        mask = None
        if mask_batch is not None:
            mask = mask_batch[0 if int(mask_batch.shape[0]) == 1 else index]
        pil_frames.append(_tensor_image_to_rgba(image_batch[index], mask))

    max_frame_width = max(frame.width for frame in pil_frames)
    max_frame_height = max(frame.height for frame in pil_frames)
    resolved_cell_width = cell_width or max_frame_width
    resolved_cell_height = cell_height or max_frame_height

    if resolved_cell_width < max_frame_width or resolved_cell_height < max_frame_height:
        raise ValueError(
            f"cell_width/cell_height 不能小于最大帧尺寸，当前最大帧为 {max_frame_width}x{max_frame_height}"
        )

    resolved_columns = columns or frame_count
    resolved_columns = max(1, resolved_columns)
    resolved_rows = math.ceil(frame_count / resolved_columns)

    sheet_width = margin * 2 + resolved_columns * resolved_cell_width + max(resolved_columns - 1, 0) * padding
    sheet_height = margin * 2 + resolved_rows * resolved_cell_height + max(resolved_rows - 1, 0) * padding

    canvas = Image.new("RGBA", (sheet_width, sheet_height), _background_rgba(background))
    frame_names = _parse_frame_names(frame_names_json, frame_count)

    frames_meta: list[dict[str, Any]] = []
    for index, (frame_name, frame_image) in enumerate(zip(frame_names, pil_frames)):
        row = index // resolved_columns
        column = index % resolved_columns

        cell_x = margin + column * (resolved_cell_width + padding)
        cell_y = margin + row * (resolved_cell_height + padding)
        offset_x = _alignment_offset(resolved_cell_width, frame_image.width, horizontal_align)
        offset_y = _alignment_offset(resolved_cell_height, frame_image.height, vertical_align)
        paste_x = cell_x + offset_x
        paste_y = cell_y + offset_y

        canvas.alpha_composite(frame_image, (paste_x, paste_y))
        frames_meta.append(
            {
                "index": index,
                "name": frame_name,
                "row": row,
                "column": column,
                "cell_x": cell_x,
                "cell_y": cell_y,
                "cell_width": resolved_cell_width,
                "cell_height": resolved_cell_height,
                "content_x": paste_x,
                "content_y": paste_y,
                "content_width": frame_image.width,
                "content_height": frame_image.height,
            }
        )

    sprite_meta = {
        "version": 1,
        "frame_count": frame_count,
        "columns": resolved_columns,
        "rows": resolved_rows,
        "cell_width": resolved_cell_width,
        "cell_height": resolved_cell_height,
        "frame_width": resolved_cell_width,
        "frame_height": resolved_cell_height,
        "sheet_width": sheet_width,
        "sheet_height": sheet_height,
        "padding": padding,
        "margin": margin,
        "horizontal_align": horizontal_align,
        "vertical_align": vertical_align,
        "background": background,
        "metadata_key": metadata_key,
        "frame_names": frame_names,
        "frames": frames_meta,
    }
    return canvas, sprite_meta


def _rgba_canvas_to_outputs(canvas: Image.Image) -> tuple[Any, Any]:
    if torch is None:  # pragma: no cover - ComfyUI runtime should provide torch
        raise RuntimeError("torch 不可用，无法处理 ComfyUI IMAGE 张量")

    rgba_array = np.asarray(canvas).astype(np.float32) / 255.0
    rgb_tensor = torch.from_numpy(rgba_array[:, :, :3])[None, ...]
    alpha_mask = torch.from_numpy(rgba_array[:, :, 3])
    return rgb_tensor, alpha_mask


def _extract_single_image_rgb(image: Any) -> np.ndarray:
    image_batch = _normalize_image_batch(image)
    if int(image_batch.shape[0]) != 1:
        raise ValueError(f"保存精灵图时 images 必须是单张图，当前 batch={int(image_batch.shape[0])}")

    image_array = np.clip(255.0 * image_batch[0].cpu().numpy(), 0, 255).astype(np.uint8)
    if image_array.ndim != 3:
        raise ValueError(f"sprite image 必须是 HWC，当前 shape={image_array.shape}")
    if image_array.shape[2] == 1:
        image_array = np.repeat(image_array, 3, axis=2)
    return image_array[:, :, :3]


def _extract_single_mask(mask: Any | None, height: int, width: int) -> np.ndarray:
    if mask is None:
        return np.full((height, width), 255, dtype=np.uint8)

    mask_batch = _normalize_mask_batch(mask)
    if int(mask_batch.shape[0]) != 1:
        raise ValueError(f"保存精灵图时 mask 必须是单张图，当前 batch={int(mask_batch.shape[0])}")

    mask_array = np.clip(255.0 * mask_batch[0].cpu().numpy(), 0, 255).astype(np.uint8)
    if mask_array.shape != (height, width):
        raise ValueError(f"mask 尺寸需要和 image 一致，当前 mask={mask_array.shape} image={(height, width)}")
    return mask_array


def _parse_sprite_metadata_json(raw: str) -> dict[str, Any]:
    text = (raw or "").strip()
    if not text:
        return {}
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("sprite_metadata_json 必须是 JSON object")
    return parsed


class OCSpriteSheetBuilder:
    CATEGORY = "oc/action"
    FUNCTION = "build_sprite_sheet"
    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("sprite_image", "sprite_mask", "sprite_metadata_json")

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        return {
            "required": {
                "images": ("IMAGE",),
                "columns": ("INT", {"default": 0, "min": 0, "max": 4096}),
                "cell_width": ("INT", {"default": 0, "min": 0, "max": 8192}),
                "cell_height": ("INT", {"default": 0, "min": 0, "max": 8192}),
                "padding": ("INT", {"default": 0, "min": 0, "max": 1024}),
                "margin": ("INT", {"default": 0, "min": 0, "max": 1024}),
                "horizontal_align": (["center", "left", "right"],),
                "vertical_align": (["bottom", "center", "top"],),
                "background": (["transparent", "white", "black"],),
                "metadata_key": ("STRING", {"default": "sprite_sheet"}),
                "frame_names_json": ("STRING", {"multiline": True, "default": ""}),
            },
            "optional": {
                "masks": ("MASK",),
            },
        }

    def build_sprite_sheet(
        self,
        images: Any,
        columns: int,
        cell_width: int,
        cell_height: int,
        padding: int,
        margin: int,
        horizontal_align: str,
        vertical_align: str,
        background: str,
        metadata_key: str,
        frame_names_json: str,
        masks: Any | None = None,
    ) -> tuple[Any, Any, str]:
        canvas, sprite_meta = _build_sprite_sheet_rgba(
            images=images,
            masks=masks,
            columns=columns,
            cell_width=cell_width,
            cell_height=cell_height,
            padding=padding,
            margin=margin,
            horizontal_align=horizontal_align,
            vertical_align=vertical_align,
            background=background,
            metadata_key=metadata_key,
            frame_names_json=frame_names_json,
        )
        sprite_image, sprite_mask = _rgba_canvas_to_outputs(canvas)
        sprite_meta_json = json.dumps(sprite_meta, ensure_ascii=False, indent=2)
        return sprite_image, sprite_mask, sprite_meta_json


class OCSpriteSheetSavePNG:
    CATEGORY = "oc/action"
    FUNCTION = "save_png"
    OUTPUT_NODE = True
    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("sprite_path", "sprite_metadata_json")

    def __init__(self) -> None:
        self.output_dir = _default_output_directory()
        self.type = "output"

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        return {
            "required": {
                "image": ("IMAGE",),
                "sprite_metadata_json": ("STRING", {"multiline": True, "default": ""}),
                "filename_prefix": ("STRING", {"default": "oc_sprite_sheet/sprite_sheet"}),
                "write_sprite_metadata": ("BOOLEAN", {"default": True}),
                "write_sidecar_json": ("BOOLEAN", {"default": True}),
                "metadata_key_override": ("STRING", {"default": ""}),
            },
            "optional": {
                "masi": ("MASK",),
            },
            "hidden": {
                "prompt": "PROMPT",
                "extra_pnginfo": "EXTRA_PNGINFO",
            },
        }

    def save_png(
        self,
        image: Any,
        sprite_metadata_json: str,
        filename_prefix: str,
        write_sprite_metadata: bool,
        write_sidecar_json: bool,
        metadata_key_override: str,
        mask: Any | None = None,
        prompt: Any | None = None,
        extra_pnginfo: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        rgb_array = _extract_single_image_rgb(image)
        alpha_array = _extract_single_mask(mask, rgb_array.shape[0], rgb_array.shape[1])
        rgba_image = Image.fromarray(np.dstack([rgb_array, alpha_array]), mode="RGBA")

        sprite_meta = _parse_sprite_metadata_json(sprite_metadata_json)
        metadata_key = metadata_key_override.strip() or str(sprite_meta.get("metadata_key", "sprite_sheet"))

        output_path, subfolder = _next_output_path(filename_prefix, self.output_dir)

        pnginfo = PngInfo()
        if prompt is not None:
            pnginfo.add_text("prompt", json.dumps(prompt))

        merged_extra_pnginfo = dict(extra_pnginfo or {})
        if write_sprite_metadata and sprite_meta:
            merged_extra_pnginfo[metadata_key] = sprite_meta

        for key, value in merged_extra_pnginfo.items():
            pnginfo.add_text(key, json.dumps(value))

        rgba_image.save(output_path, pnginfo=pnginfo, optimize=True)

        if write_sidecar_json and sprite_meta:
            output_path.with_suffix(".sprite.json").write_text(
                json.dumps(sprite_meta, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        return {
            "ui": {
                "images": [
                    {
                        "filename": output_path.name,
                        "subfolder": subfolder,
                        "type": self.type,
                    }
                ]
            },
            "result": (str(output_path), json.dumps(sprite_meta, ensure_ascii=False, indent=2)),
        }


NODE_CLASS_MAPPINGS = {
    "OCSpriteSheetBuilder": OCSpriteSheetBuilder,
    "OCSpriteSheetSavePNG": OCSpriteSheetSavePNG,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "OCSpriteSheetBuilder": "OC Sprite Sheet Builder",
    "OCSpriteSheetSavePNG": "OC Sprite Sheet Save PNG",
}
