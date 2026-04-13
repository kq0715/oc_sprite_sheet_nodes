# OC Sprite Sheet Nodes

把整个文件夹：

- `oc_sprite_sheet_nodes`

直接放到：

- `ComfyUI/custom_nodes/`

重启 ComfyUI 后即可使用。

## 包含节点

- `OC Sprite Sheet Builder`
- `OC Sprite Sheet Save PNG`

## 推荐串法

1. `OC Sprite Sheet Builder`
2. 其他图片处理节点
3. `OC Sprite Sheet Save PNG`

## 文件说明

- `__init__.py`
  - ComfyUI 节点入口
- `sprite_sheet_node.py`
  - 节点实现
- `SPRITE_SHEET_NODE.md`
  - 详细文档

## 适合场景

- 把动作帧批量图拼成 sprite sheet
- 输出图片后继续接其他节点处理
- 最后再选择是否带 `prompt/workflow/sprite_sheet` 元数据保存为 PNG
