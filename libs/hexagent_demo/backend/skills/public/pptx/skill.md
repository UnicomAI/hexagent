---
name: pptx
description: "处理 .pptx 文件（创建、读取、编辑、合并、拆分）。支持幻灯片生成、图表添加。在处理演示文稿、deck 或 slides 时触发。"
license: 专有软件。完整条款请参阅 LICENSE.txt
---

# PPTX Plus Skill (Linux)

**核心原则：渐进式披露**
本技能的核心是渐进式披露。`skill.md` 包含最重要的原则、工作流和目录，当需要执行具体任务时，再去读取相应的 markdown 指南。

## 标准工作流（从零创建 PPT）

当需要从零开始创建 PPT 时，**必须**遵循以下固定工作流：

1. **素材处理（可有可无）**：如果用户上传了素材，**一定要优先处理并使用用户的素材**，阅读 `uploadprocess.md`。
2. **联网调研（可有可无）**：如果用户没有素材或要求调研，阅读 `websearch.md` 进行联网搜索。
3. **生成调研报告**：基于素材或搜索结果，生成包含具体数据的 `research.md`。
4. **压缩上下文**：清理多余历史，重新加载本 skills。
5. **读取调研报告**：读取生成的 `research.md`。
6. **生成大纲**：阅读 `outlineWriting.md` 和 `pptxgenjs.md`，然后输出 `outline.json`。
7. **分批写入 JS**：阅读下方的「⚠️ 重要：分批写入策略」，根据 `outline.json`（仅作参考，需灵活调整防止重叠）编写 JS。
8. **JS 转 PPTX**：执行 JS 脚本生成最终的 PPTX 文件。

## 快速参考

| 任务            | 指南                                           |
| --------------- | ---------------------------------------------- |
| 读取/分析内容   | `python -m markitdown presentation.pptx`       |
| 编辑/修改       | 阅读 [editing.md](editing.md)                  |
| 处理用户素材    | 阅读 [uploadprocess.md](uploadprocess.md)      |
| 联网调研        | 阅读 [websearch.md](websearch.md)              |
| 生成大纲        | 阅读 [outlineWriting.md](outlineWriting.md)    |
| 从零创建(JS)    | 阅读 [pptxgenjs.md](pptxgenjs.md)              |
| 可视化检查与 QA | 阅读 [examin.md](examin.md) (仅用户要求时使用) |
| **添加图表**    | 见下方「图表生成」章节                         |

---

## ⚠️ 重要：分批写入策略

**使用 PptxGenJS 创建 PPTX 时，务必采用分批写入以避免 token 溢出错误。**

### 为什么要分批写入？

生成复杂、视觉效果丰富的演示文稿时，代码可能变得非常长。在单次响应中写入所有幻灯片可能导致 token 溢出错误。**分批写入同一个文件可解决此问题。**

### 如何分批写入

1. **严格限制：每批最多 5 张幻灯片** — 5 张是最佳选择。
2. **一个文件，多次编辑**：所有代码必须写入**同一个 JavaScript 文件**。不要为不同批次创建多个文件。
3. **增量追加策略**：使用 Edit 工具将新幻灯片代码**追加**到现有文件中。每批应继续使用第一批中定义的同一个 `pres` 对象。
4. **构建支持增量添加的代码结构：**

```javascript
// 批次 1：初始化设置 + 幻灯片 1-5
const pptxgen = require('pptxgenjs')

let pres = new pptxgen()
pres.layout = 'LAYOUT_16x9'

// 幻灯片 1-5 代码在此...
// 可选的增量保存检查点

// --- 批次 1 结束 ---

// 批次 2：幻灯片 6-10（继续向同一个 pres 对象添加）
// 更多幻灯片代码...

// 批次 N：最终保存
pres.writeFile({ fileName: 'output.pptx' })
```

### 分批写入工作流

```
步骤 1：写入初始设置 + 幻灯片 1-5 → 保存/继续
步骤 2：写入幻灯片 6-10 → 继续使用同一个 pres 对象
步骤 3：写入幻灯片 11-15 → 继续
...
最终：写入幻灯片 N-M + pres.writeFile()
```

**请记住：** 你是增量地向同一个 JavaScript 文件添加内容。每批向文件添加更多代码，而不是创建单独的文件。

---

## 读取内容

```bash
# 文本提取
python -m markitdown presentation.pptx

# 可视化概览
python scripts/thumbnail.py presentation.pptx

# 原始 XML
python scripts/office/unpack.py presentation.pptx unpacked/
```

---

## 编辑工作流

**完整详情请阅读** **[editing.md](editing.md)。**

1. 使用 `thumbnail.py` 分析模板
2. 解包 → 操作幻灯片 → 编辑内容 → 清理 → 打包

---

## 图表生成

**为演示文稿添加精美图表，让数据可视化更具冲击力。**

### 图表类型选择指南

根据数据特征选择最合适的图表类型：

| 数据类型     | 推荐图表                                                                                                             | 用途                                         |
| ------------ | -------------------------------------------------------------------------------------------------------------------- | -------------------------------------------- |
| **时间序列** | `line_chart`, `area_chart`                                                                                           | 趋势、累积变化                               |
| **对比**     | `bar_chart`, `column_chart`                                                                                          | 类别对比、Top-N 排行                         |
| **占比**     | `pie_chart`, `treemap_chart`                                                                                         | 整体与部分、层级占比                         |
| **相关性**   | `scatter_chart`, `dual_axes_chart`                                                                                   | 变量关系、双轴对比                           |
| **流程**     | `funnel_chart`, `flow_diagram`                                                                                       | 转化漏斗、流程步骤                           |
| **分布**     | `histogram_chart`, `boxplot_chart`, `violin_chart`                                                                   | 频率分布、统计分布                           |
| **层级**     | `organization_chart`, `mind_map`                                                                                     | 组织结构、思维导图                           |
| **地理**     | `district_map`, `pin_map`, `path_map`                                                                                | 区域数据、点位、路线                         |
| **专项**     | `radar_chart`, `liquid_chart`, `word_cloud_chart`, `network_graph`, `sankey_chart`, `venn_chart`, `fishbone_diagram` | 多维对比、进度、词频、网络、流向、交集、因果 |

### 图表生成方法

#### 方法一：图片图表（推荐用于复杂图表）

生成高质量图表图片，然后插入幻灯片。适合需要精美视觉效果或复杂图表类型。

```bash
# 生成图表图片
node scripts/generate.js '{"tool":"generate_pie_chart","args":{"data":[{"category":"A","value":35},{"category":"B","value":45},{"category":"C","value":20}],"title":"市场份额","theme":"dark"}}'
```

返回图表图片 URL，然后在 JavaScript 中使用：

```javascript
// 在 PptxGenJS 中插入图表图片
slide.addImage({
  path: '返回的图表URL',
  x: 0.5,
  y: 1.5,
  w: 4.5,
  h: 3.5
})
```

**图表参数规格详见** **[references/](references/)** **目录下的各图表文档。**

#### 方法二：原生图表（适合简单图表）

使用 PptxGenJS 内置图表功能，适合快速创建简单柱状图、折线图、饼图。

```javascript
// 柱状图
slide.addChart(pres.charts.BAR, [{
  name: '销售额',
  labels: ['Q1', 'Q2', 'Q3', 'Q4'],
  values: [4500, 5500, 6200, 7100]
}], {
  x: 0.5,
  y: 0.6,
  w: 6,
  h: 3,
  barDir: 'col',
  showTitle: true,
  title: '季度销售',
  chartColors: ['0D9488', '14B8A6', '5EEAD4'],
  showValue: true,
  dataLabelPosition: 'outEnd'
})

// 饼图
slide.addChart(pres.charts.PIE, [{
  name: '份额',
  labels: ['A', 'B', '其他'],
  values: [35, 45, 20]
}], { x: 7, y: 1, w: 5, h: 4, showPercent: true })
```

### 方法选择建议

| 场景                             | 推荐方法 | 原因             |
| -------------------------------- | -------- | ---------------- |
| 简单柱状/折线/饼图               | 原生图表 | 快速、代码简洁   |
| 需要与PPT主题配色统一            | 原生图表 | 可自定义颜色     |
| 复杂图表类型（雷达图、桑基图等） | 图片图表 | 原生不支持       |
| 需要精美视觉效果                 | 图片图表 | 更丰富的视觉样式 |
| 需要动态交互                     | 原生图表 | 可在PPT中编辑    |
| 暗色主题/特殊样式                | 图片图表 | 支持多种主题     |

### 图表主题与样式

图片图表支持三种主题：

- `default` - 标准白色背景
- `dark` - 深色背景，适合深色PPT
- `academy` - 学术风格

自定义配色：

```json
{
  "tool": "generate_column_chart",
  "args": {
    "data": [...],
    "title": "销售数据",
    "theme": "dark",
    "style": {
      "palette": ["#1E2761", "#CADCFC", "#FFFFFF"],
      "backgroundColor": "#1a1a2e"
    }
  }
}
```

### 详细图表规格

每种图表的完整参数说明，请参阅对应的参考文档：

- `references/generate_line_chart.md` - 折线图
- `references/generate_bar_chart.md` - 条形图
- `references/generate_column_chart.md` - 柱状图
- `references/generate_pie_chart.md` - 饼图/环图
- `references/generate_area_chart.md` - 面积图
- `references/generate_scatter_chart.md` - 散点图
- `references/generate_radar_chart.md` - 雷达图
- `references/generate_funnel_chart.md` - 漏斗图
- `references/generate_treemap_chart.md` - 树图
- `references/generate_sankey_chart.md` - 桑基图
- `references/generate_dual_axes_chart.md` - 双轴图
- 以及其他 15+ 种图表类型

---

## 从零创建

**完整详情请阅读** **[pptxgenjs.md](pptxgenjs.md)。**

从零创建时，请严格按照前文所述的“标准工作流”执行。
**注意：** 如果用户上传了素材，一定要优先处理并使用用户的素材，而不是去进行联网搜索。

---

## 设计思路

**不要创建无聊的幻灯片。** 白底黑字的简单列表无法打动任何人。为每张幻灯片考虑以下设计思路。

### 开始之前

- **选择大胆、契合内容的配色方案**：配色应为此主题量身设计。如果将你的配色方案换到一个完全不同的演示文稿中仍然"适用"，说明你的选择还不够具体。
- **主次分明而非均等分配**：一种颜色应占主导地位（60-70% 视觉权重），配以 1-2 种辅助色调和一种锐利的强调色。永远不要给所有颜色相等的权重。
- **深浅对比**：标题 + 结尾幻灯片使用深色背景，内容幻灯片使用浅色背景（"三明治"结构）。或者全程使用深色背景以营造高端感。
- **坚持一个视觉母题**：选择一个独特的元素并重复使用 —— 圆角图片框、彩色圆形图标、单侧粗边框。在每张幻灯片中贯彻使用。

### 配色方案

选择与主题匹配的颜色 —— 不要默认使用通用蓝色。以下配色方案供参考：

| 主题           | 主色               | 辅色               | 强调色             |
| -------------- | ------------------ | ------------------ | ------------------ |
| **午夜高管**   | `1E2761`（藏蓝）   | `CADCFC`（冰蓝）   | `FFFFFF`（白色）   |
| **森林苔藓**   | `2C5F2D`（森林绿） | `97BC62`（苔藓绿） | `F5F5F5`（奶油色） |
| **珊瑚活力**   | `F96167`（珊瑚红） | `F9E795`（金色）   | `2F3C7E`（藏蓝）   |
| **暖赤陶**     | `B85042`（赤陶色） | `E7E8D1`（沙色）   | `A7BEAE`（鼠尾草） |
| **海洋渐变**   | `065A82`（深海蓝） | `1C7293`（青色）   | `21295C`（午夜蓝） |
| **炭灰极简**   | `36454F`（炭灰）   | `F2F2F2`（灰白）   | `212121`（黑色）   |
| **青绿信赖**   | `028090`（青色）   | `00A896`（海泡色） | `02C39A`（薄荷绿） |
| **浆果奶油**   | `6D2E46`（浆果色） | `A26769`（玫瑰灰） | `ECE2D0`（奶油色） |
| **鼠尾草宁静** | `84B59F`（鼠尾草） | `69A297`（桉树绿） | `50808E`（板岩灰） |
| **樱桃大胆**   | `990011`（樱桃红） | `FCF6F5`（灰白）   | `2F3C7E`（藏蓝）   |

### 每张幻灯片

**每张幻灯片都需要一个视觉元素** —— 图片、图表、图标或形状。纯文字的幻灯片容易被遗忘。

**布局选项：**

- 双栏（左侧文字，右侧插图）
- 图标 + 文字行（彩色圆圈中的图标，粗体标题，下方描述）
- 2x2 或 2x3 网格（一侧放图片，另一侧放内容块网格）
- 半出血图片（完整的左侧或右侧）配内容覆盖

**数据展示：**

- 大号数据突出（60-72pt 大数字，下方小标签）
- 对比栏（前后对比、优缺点、并排选项）
- 时间线或流程图（编号步骤，箭头）
- **精美图表**（使用图表生成功能，数据可视化更具冲击力）

**视觉打磨：**

- 章节标题旁的小彩色圆圈图标
- 关键数据或标语使用斜体强调文字

### 排版

**选择有趣的字体搭配** —— 不要默认使用 Arial。选择有个性的标题字体，搭配清晰的正文字体。

| 标题字体     | 正文字体      |
| ------------ | ------------- |
| Georgia      | Calibri       |
| Arial Black  | Arial         |
| Calibri      | Calibri Light |
| Cambria      | Calibri       |
| Trebuchet MS | Calibri       |
| Impact       | Arial         |
| Palatino     | Garamond      |
| Consolas     | Calibri       |

| 元素       | 字号         |
| ---------- | ------------ |
| 幻灯片标题 | 36-44pt 粗体 |
| 章节标题   | 20-24pt 粗体 |
| 正文文本   | 14-16pt      |
| 说明文字   | 10-12pt 弱化 |

### 间距

- 最小边距 0.5 英寸
- 内容块之间 0.3-0.5 英寸
- 留出呼吸空间 —— 不要填满每一寸

### 避免事项（常见错误）

- **不要重复使用相同布局** —— 在幻灯片间变化使用栏、卡片和突出显示
- **正文不要居中** —— 段落和列表左对齐；只有标题居中
- **不要吝啬字号对比** —— 标题需要 36pt+ 才能与 14-16pt 正文区分
- **不要默认使用蓝色** —— 选择反映特定主题的颜色
- **不要随意混合间距** —— 选择 0.3" 或 0.5" 间隙并保持一致
- **不要只设计一张幻灯片而让其他保持朴素** —— 要么完全投入，要么全程保持简洁
- **不要创建纯文字幻灯片** —— 添加图片、图标、图表或视觉元素；避免纯标题 + 列表
- **不要忘记文本框内边距** —— 当将线条或形状与文本边缘对齐时，在文本框上设置 `margin: 0` 或偏移形状以考虑内边距
- **不要使用低对比度元素** —— 图标和文字都需要与背景形成强对比；避免浅色背景上的浅色文字或深色背景上的深色文字
- **绝对不要在标题下使用装饰线** —— 这是 AI 生成幻灯片的标志；改用留白或背景色
- **绝对不要在 JavaScript 中使用中文引号（如：" "）** —— 会导致 PptxGenJS 崩溃或生成损坏文件；始终使用标准 ASCII 引号（`' '` 或 `" "`）

### 设计质量检查清单

创建完幻灯片后，对照以下清单进行自我检查：

**布局与对齐**

- [ ] 图片、表格、图表是否对齐（底部或顶部对齐）？
- [ ] 文字块之间间距是否一致（统一使用 0.3" 或 0.5"）？
- [ ] 是否避免了"后加"的感觉——底部内容是否与整体融为一体？

**视觉层次**

- [ ] 标题字号是否足够大（36pt+）与正文区分？
- [ ] 是否有清晰的视觉焦点（主图、核心数据、关键结论）？
- [ ] 信息密度是否适中——既不拥挤也不空洞？

**图表与图片**

- [ ] 图表颜色是否与整体配色方案协调？
- [ ] 图表是否与文物/照片风格统一？
- [ ] 图表是否放置在合适的位置——不是孤立在角落？

**内容完整性**

- [ ] 每张幻灯片是否有明确的单一主题？
- [ ] 数据是否有来源标注？
- [ ] 结论是否清晰可见？

**可视化检查**

```bash
# 生成缩略图检查整体效果
python scripts/ppt_to_pic.py --file presentation.pptx --output thumbnails

# 使用 Qwen 视觉分析
python scripts/vision_qwen.py --image thumbnails/slide1.PNG --prompt "分析这张幻灯片的设计质量和改进建议"
```

---

## 依赖项

**核心依赖：**

- `pip install "markitdown[pptx]"` - 文本提取
- `pip install Pillow` - 缩略图网格
- `npm install -g pptxgenjs` - 从零创建
- LibreOffice (`soffice`) - PDF 转换（Linux）
- Poppler (`pdftoppm`) - PDF 转图片

**可视化工具：**

- `pip install svglib reportlab` - SVG 转 PNG，用于视觉工具

**图表生成：**

- Node.js >= 18.0.0 - 运行图表生成脚本

---

## 环境设置

为获得可视化工具和生成工具的最佳效果：

```bash
# 验证图表生成
node scripts/generate.js '{"tool":"generate_column_chart","args":{"data":[{"category":"测试","value":100}],"title":"测试图表"}}'

# 验证 LibreOffice 安装
soffice --version

# 验证 pdftoppm 安装
pdftoppm -v
```
