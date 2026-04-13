# OC Sprite Sheet Nodes

## 作用

把 ComfyUI 工作流最后输出的 `N` 张图，拼成一张精灵图（sprite sheet）。

适合场景：

- 动作资源生成工作流的最后一步
- 把一批动作帧导出成单张 sprite sheet
- 同时把切图信息写进 PNG 元数据，方便下游读取

## 节点名

- `OC Sprite Sheet Builder`
- `OC Sprite Sheet Save PNG`

推荐串法：

1. `OC Sprite Sheet Builder`
2. 你的后续图片节点
3. `OC Sprite Sheet Save PNG`（如果最后需要带元数据落盘）

## Builder 节点

### 作用

输入 `IMAGE` 批量图，输出拼好的精灵图。

### 输出

- `sprite_image`
- `sprite_mask`
- `sprite_metadata_json`

### 输入

- `images`
  - ComfyUI 的 `IMAGE` 批量图
- `columns`
  - 每行放几格
  - `0` 表示自动用单行排布
- `cell_width`
  - 每格框宽
  - `0` 表示自动取输入帧里的最大宽度
- `cell_height`
  - 每格框高
  - `0` 表示自动取输入帧里的最大高度
- `padding`
  - 格子之间的间距
- `margin`
  - 精灵图四周外边距
- `horizontal_align`
  - 帧图在格子里的水平对齐方式
  - 支持 `left / center / right`
- `vertical_align`
  - 帧图在格子里的垂直对齐方式
  - 支持 `top / center / bottom`
  - 默认建议用 `bottom`，角色动作帧更稳，不容易脚底漂
- `background`
  - 精灵图背景
  - 支持 `transparent / white / black`
- `frame_names_json`
  - 可选
  - 用来写入每帧名字
  - 需要是字符串数组，长度必须和输入帧数一致
- `masks`
  - 可选
  - 如果你有透明遮罩，可以一起输入，节点会写到 alpha 通道里

### 关于“输入图片然后输出图片”

这一版已经改成纯图片处理节点了：

- 输入：`IMAGE`
- 输出：`IMAGE + MASK + STRING`

所以你后面可以直接把 `sprite_image` 接到别的图片节点，不会被保存节点卡住。

## Save PNG 节点

### 作用

把 `Builder` 产出的精灵图和元数据真正写成 PNG。

### 输入

- `image`
  - 一张精灵图
- `mask`
  - 可选
  - 对应精灵图的 alpha mask
- `sprite_metadata_json`
  - 来自 `Builder`
- `filename_prefix`
  - 输出文件名前缀
- `write_sprite_metadata`
  - 是否把 `sprite_sheet` 写入 PNG 顶层扩展字段
- `write_sidecar_json`
  - 是否额外输出同名 `.sprite.json`
- `metadata_key_override`
  - 可选
  - 覆盖默认元数据键名

## 关于“每格的框高写哪”

就写在 `Builder` 节点的：

- `cell_height`

如果下游资源系统对每帧框高有固定要求，直接把那个值填进 `cell_height`。

如果还没有固定规范：

- `cell_height = 0`

节点会自动取本批图片里的最大高度作为统一格高。

## 精灵图规范

ComfyUI 本身没有通用的 sprite sheet 标准字段。

所以这版节点做了两层输出：

1. PNG 元数据
   - `OC Sprite Sheet Save PNG` 会把 `sprite_sheet` 信息写进 PNG text metadata
   - 它和 ComfyUI 的 `prompt`、`workflow` 一样，都是顶层扩展字段
2. sidecar JSON
   - `OC Sprite Sheet Save PNG` 同路径额外输出一个 `.sprite.json`
   - 方便服务端或脚本直接读

如果你想改元数据键名，可以改：

- `metadata_key`

默认是：

- `sprite_sheet`

## 元数据结构

默认会写出一份类似这样的结构：

```json
{
  "version": 1,
  "frame_count": 4,
  "columns": 4,
  "rows": 1,
  "cell_width": 768,
  "cell_height": 768,
  "frame_width": 768,
  "frame_height": 768,
  "sheet_width": 3072,
  "sheet_height": 768,
  "padding": 0,
  "margin": 0,
  "horizontal_align": "center",
  "vertical_align": "bottom",
  "background": "transparent",
  "frame_names": [
    "walk_right_90_00001_",
    "walk_right_90_00002_",
    "walk_right_90_00003_",
    "walk_right_90_00004_"
  ],
  "frames": [
    {
      "index": 0,
      "name": "walk_right_90_00001_",
      "row": 0,
      "column": 0,
      "cell_x": 0,
      "cell_y": 0,
      "cell_width": 768,
      "cell_height": 768,
      "content_x": 12,
      "content_y": 20,
      "content_width": 744,
      "content_height": 748
    }
  ]
}
```

## 输出

`Builder` 输出：

- `sprite_image`
- `sprite_mask`
- `sprite_metadata_json`

`Save PNG` 输出：

- 一张 PNG 精灵图
- 一份 PNG 内嵌元数据
- 一份同名 `.sprite.json`
- 返回 `sprite_path`

## 推荐用法

### 1. 单行动画条

- `Builder.columns = 0`
- `Builder.cell_width = 0`
- `Builder.cell_height = 0`
- `Builder.vertical_align = bottom`

适合：

- walk 4 帧
- breathe 4 帧
- show 12 帧

### 2. 固定切图规格

如果你下游约定每格必须是 `768 x 768`：

- `Builder.cell_width = 768`
- `Builder.cell_height = 768`

这样即使原始帧大小略有差异，也会统一落到固定格子里。

## 注意

- 如果 `cell_width / cell_height` 小于输入帧最大尺寸，节点会直接报错，不会偷偷裁图
- 如果没有 `masks` 输入，且上游 `IMAGE` 也不带 alpha，就会输出/保存为不透明图
- 角色动作帧通常建议：
  - `horizontal_align = center`
  - `vertical_align = bottom`
  - `background = transparent`
