# 大纲生成指南 (Outline Writing)

**重要说明：** 这个环节发生在素材准备就绪之后、真正开始编写 PPT 代码之前。

## 生成大纲的步骤

1. **阅读基础文档**
   在编写大纲前，请先完整阅读以下两个文档：
   - 当前的 `outlineWriting.md` (本文件)
   - `pptxgenjs.md` (了解排版和样式的可用性)

2. **输出 `outline.json`**
   你需要基于调研报告 `research.md`，写出一个 `outline.json` 文件。
   这个文件包含了每一页 PPT 的主要内容和详细的排版文字描述。

### `outline.json` 格式要求

每一页的规划需要包含以下字段：
- **`slide_number`**: 幻灯片页码
- **`page_type`**: 这一页的类型（如：封面页 / 目录页 / 内容页 / 结束页 等）
- **`core_message`**: 这一页主要想要给大家展示什么震撼的核心内容（概括性描述，不要在此写具体的数据文本）
- **`color_scheme`**: 选用的配色方案（如背景色、主色、强调色等）
- **`visual_elements`**: 准备放置哪些视觉素材（如图表、图片、图标）
- **`layout_description`**: 这些元素应该怎么排放（如：“左侧大图半出血，右侧文字居中对齐”、“顶部大标题，下方三个带图标的列并排”等）

**示例：**
```json
[
  {
    "slide_number": 1,
    "page_type": "封面页",
    "core_message": "展示2026年AI市场爆发式增长的震撼开场",
    "color_scheme": "深色背景 (午夜蓝)，文字为白色，辅以青色强调",
    "visual_elements": ["全屏科技感背景图", "半透明覆盖层"],
    "layout_description": "背景图全屏铺满，中间放置大字号的主标题，下方小字号副标题居中对齐"
  },
  {
    "slide_number": 2,
    "page_type": "内容页",
    "core_message": "揭示三项核心技术的占比差异",
    "color_scheme": "浅色背景 (灰白)，图表使用品牌色",
    "visual_elements": ["环形图 (Pie Chart)"],
    "layout_description": "左侧为大号加粗文本和核心结论，右侧放置环形图，整体采用左右两栏对称布局"
  }
]
```

## 下一步提醒
完成 `outline.json` 后，你将进入分批编写 JavaScript 的环节。
请记住：**`outline.json` 里面的规划并不完美，它只是帮你做了大致的构思和灵感。** 具体细节仍需打磨，在写 JS 代码时可以随时调整。请务必根据具体情况做出最终精美的设计，**尤其注意元素不要重叠，否则会极大地影响观感。**
