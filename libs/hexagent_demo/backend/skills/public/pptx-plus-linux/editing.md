# 编辑演示文稿

## 基于模板的工作流

使用现有演示文稿作为模板时：

1. **分析现有幻灯片**：
   ```bash
   python scripts/thumbnail.py template.pptx
   python -m markitdown template.pptx
   ```
   查看 `thumbnails.jpg` 了解布局，查看 markitdown 输出了解占位符文本。

2. **规划幻灯片映射**：为每个内容部分选择一个模板幻灯片。

   ⚠️ **使用多样化的布局** —— 布局单调是常见的失败模式。不要默认使用基本的标题 + 列表幻灯片。主动寻找：
   - 多栏布局（双栏、三栏）
   - 图片 + 文字组合
   - 全出血图片配文字覆盖
   - 引用或强调幻灯片
   - 章节分隔页
   - 数据/数字突出显示
   - 图标网格或图标 + 文字行

   **避免：** 每张幻灯片重复使用相同的文字密集型布局。

   将内容类型与布局风格匹配（如：要点 → 列表幻灯片，团队信息 → 多栏，证言 → 引用幻灯片）。

3. **解包**：`python scripts/office/unpack.py template.pptx unpacked/`

4. **构建演示文稿**（自己完成，不要使用子代理）：
   - 删除不需要的幻灯片（从 `<p:sldIdLst>` 中移除）
   - 复制要重用的幻灯片（`add_slide.py`）
   - 在 `<p:sldIdLst>` 中重新排序幻灯片
   - **在步骤 5 之前完成所有结构性更改**

5. **编辑内容**：更新每个 `slide{N}.xml` 中的文本。
   **如果可用，在此处使用子代理** —— 幻灯片是独立的 XML 文件，所以子代理可以并行编辑。

6. **清理**：`python scripts/clean.py unpacked/`

7. **打包**：`python scripts/office/pack.py unpacked/ output.pptx --original template.pptx`

---

## 脚本

| 脚本 | 用途 |
|------|------|
| `unpack.py` | 解压并格式化 PPTX |
| `add_slide.py` | 复制幻灯片或从布局创建 |
| `clean.py` | 删除孤立文件 |
| `pack.py` | 验证后重新打包 |
| `thumbnail.py` | 创建幻灯片可视化网格 |

### unpack.py

```bash
python scripts/office/unpack.py input.pptx unpacked/
```

解压 PPTX，格式化 XML，转义智能引号。

### add_slide.py

```bash
python scripts/add_slide.py unpacked/ slide2.xml      # 复制幻灯片
python scripts/add_slide.py unpacked/ slideLayout2.xml # 从布局创建
```

打印要添加到 `<p:sldIdLst>` 中所需位置的 `<p:sldId>`。

### clean.py

```bash
python scripts/clean.py unpacked/
```

删除不在 `<p:sldIdLst>` 中的幻灯片、未引用的媒体、孤立的关系文件。

### pack.py

```bash
python scripts/office/pack.py unpacked/ output.pptx --original input.pptx
```

验证、修复、压缩 XML、重新编码智能引号。

### thumbnail.py

```bash
python scripts/thumbnail.py input.pptx [output_prefix] [--cols N]
```

创建 `thumbnails.jpg`，以幻灯片文件名作为标签。默认 3 列，每网格最多 12 张。

**仅用于模板分析**（选择布局）。对于可视化 QA，使用 `soffice` + `pdftoppm` 创建全分辨率单张幻灯片图片 —— 见 SKILL.md。

---

## 幻灯片操作

幻灯片顺序在 `ppt/presentation.xml` → `<p:sldIdLst>` 中。

**重新排序**：重新排列 `<p:sldId>` 元素。

**删除**：移除 `<p:sldId>`，然后运行 `clean.py`。

**添加**：使用 `add_slide.py`。永远不要手动复制幻灯片文件 —— 脚本会处理手动复制会遗漏的备注引用、Content_Types.xml 和关系 ID。

---

## 编辑内容

**子代理：** 如果可用，在此处使用（完成步骤 4 后）。每张幻灯片是独立的 XML 文件，所以子代理可以并行编辑。在给子代理的提示中包含：
- 要编辑的幻灯片文件路径
- **"所有更改使用 Edit 工具"**
- 下面的格式规则和常见陷阱

对于每张幻灯片：
1. 读取幻灯片的 XML
2. 识别所有占位符内容 —— 文本、图片、图表、图标、说明文字
3. 用最终内容替换每个占位符

**使用 Edit 工具，而不是 sed 或 Python 脚本。** Edit 工具强制明确要替换什么和在哪里替换，从而提供更好的可靠性。

### 格式规则

- **所有标题、副标题和行内标签加粗**：在 `<a:rPr>` 上使用 `b="1"`。包括：
  - 幻灯片标题
  - 幻灯片内的章节标题
  - 行首的行内标签（如："状态："、"描述："）
- **永远不要使用 unicode 项目符号（•）**：使用正确的列表格式 `<a:buChar>` 或 `<a:buAutoNum>`
- **项目符号一致性**：让项目符号从布局继承。只指定 `<a:buChar>` 或 `<a:buNone>`。

---

## 常见陷阱

### 模板适配

当源内容项目少于模板时：
- **完全删除多余元素**（图片、形状、文本框），不要只清除文本
- 清除文本内容后检查孤立的视觉元素
- 进行可视化 QA 以发现数量不匹配

用不同长度的内容替换文本时：
- **更短的替换**：通常安全
- **更长的替换**：可能溢出或意外换行
- 文本更改后用可视化 QA 测试
- 考虑截断或拆分内容以适应模板的设计约束

**模板槽位 ≠ 源项目**：如果模板有 4 个团队成员但源有 3 个用户，删除第 4 个成员的整个组（图片 + 文本框），而不只是文本。

### 多项内容

如果源有多项内容（编号列表、多个部分），为每项创建单独的 `<a:p>` 元素 —— **永远不要连接成一个字符串**。

**❌ 错误** —— 所有项目在一个段落中：
```xml
<a:p>
  <a:r><a:rPr .../><a:t>步骤 1：做第一件事。步骤 2：做第二件事。</a:t></a:r>
</a:p>
```

**✅ 正确** —— 分开的段落配粗体标题：
```xml
<a:p>
  <a:pPr algn="l"><a:lnSpc><a:spcPts val="3919"/></a:lnSpc></a:pPr>
  <a:r><a:rPr lang="en-US" sz="2799" b="1" .../><a:t>步骤 1</a:t></a:r>
</a:p>
<a:p>
  <a:pPr algn="l"><a:lnSpc><a:spcPts val="3919"/></a:lnSpc></a:pPr>
  <a:r><a:rPr lang="en-US" sz="2799" .../><a:t>做第一件事。</a:t></a:r>
</a:p>
<a:p>
  <a:pPr algn="l"><a:lnSpc><a:spcPts val="3919"/></a:lnSpc></a:pPr>
  <a:r><a:rPr lang="en-US" sz="2799" b="1" .../><a:t>步骤 2</a:t></a:r>
</a:p>
<!-- 继续此模式 -->
```

从原始段落复制 `<a:pPr>` 以保留行间距。在标题上使用 `b="1"`。

### 智能引号

由 unpack/pack 自动处理。但 Edit 工具会将智能引号转换为 ASCII。

**添加带引号的新文本时，使用 XML 实体：**

```xml
<a:t>the &#x201C;Agreement&#x201D;</a:t>
```

| 字符 | 名称 | Unicode | XML 实体 |
|------|------|---------|----------|
| `"` | 左双引号 | U+201C | `&#x201C;` |
| `"` | 右双引号 | U+201D | `&#x201D;` |
| `'` | 左单引号 | U+2018 | `&#x2018;` |
| `'` | 右单引号 | U+2019 | `&#x2019;` |

### 其他

- **空白**：在有前导/尾随空格的 `<a:t>` 上使用 `xml:space="preserve"`
- **XML 解析**：使用 `defusedxml.minidom`，而非 `xml.etree.ElementTree`（会破坏命名空间）
