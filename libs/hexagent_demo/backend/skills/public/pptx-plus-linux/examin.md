# PPTX Plus Examination & QA (Linux)

## 可视化工具（PPT 转图片）

将 PPTX 幻灯片转换为图片以便进行可视化检查和 AI 审核。

```bash
# 将目录中所有 PPTX 文件转换为图片
python scripts/ppt_to_pic.py --ppt-dir ./ppt --output-dir ./images

# 将单个 PPTX 文件转换为图片
python scripts/ppt_to_pic.py --file presentation.pptx --output ./images

# 输出：为每个 PPTX 的幻灯片创建 JPG 图片
```

### Qwen Vision 图片描述

使用 Qwen Vision 分析和描述图片：

```bash
# 描述单张图片
python scripts/vision_qwen.py --image path/to/image.png --prompt "描述这张幻灯片"

# 批量描述多张图片（每批最多 5 张）
python scripts/vision_qwen.py --images img1.png img2.png img3.png
```

**使用场景：**
- 分析生成的幻灯片进行可视化 QA
- 描述参考图片获取设计灵感
- 从截图中提取文本和布局信息

---

## QA（必需）

**假设存在问题。你的任务是找出它们。**

你的第一次渲染几乎从来不是正确的。将 QA 视为 bug 狩猎，而非确认步骤。如果在第一次检查时没有发现问题，说明你检查得不够仔细。

### 内容 QA

```bash
python -m markitdown output.pptx
```

检查缺失内容、错别字、错误顺序。

**使用模板时，检查残留的占位符文本：**

```bash
python -m markitdown output.pptx | grep -iE "xxxx|lorem|ipsum|this.*(page|slide).*layout"
```

如果 grep 返回结果，在声明成功前修复它们。

### 可视化 QA

**⚠️ 使用子代理** —— 即使只有 2-3 张幻灯片。你一直在盯着代码，会看到你期望看到的内容，而不是实际存在的内容。子代理有全新的视角。

将幻灯片转换为图片（见[转换为图片](#转换为图片)），然后使用此提示：

```
可视化检查这些幻灯片。假设存在问题 —— 找出它们。

查找：
- 重叠元素（文字穿过形状、线条穿过文字、堆叠元素）
- 文字溢出或在边缘/框边界处被截断
- 为单行文本定位的装饰线，但标题换行成了两行
- 来源引用或页脚与上方内容冲突
- 元素过近（< 0.3" 间隙）或卡片/区块几乎接触
- 间隙不均匀（一处大面积空白，另一处拥挤）
- 距幻灯片边缘边距不足（< 0.5"）
- 列或类似元素未一致对齐
- 低对比度文字（如奶油色背景上的浅灰色文字）
- 低对比度图标（如深色背景上的深色图标，没有对比色圆圈）
- 文本框过窄导致过度换行
- 残留的占位符内容

对于每张幻灯片，列出问题或关注点，即使是次要的。

读取并分析这些图片：
1. /path/to/slide-01.jpg（预期：[简要描述]）
2. /path/to/slide-02.jpg（预期：[简要描述]）

报告发现的所有问题，包括次要问题。
```

### 验证循环

1. 生成幻灯片 → 转换为图片 → 检查
2. **列出发现的问题**（如果没有发现问题，更批判性地再次查看）
3. 修复问题
4. **重新验证受影响的幻灯片** —— 一个修复经常会引发另一个问题
5. 重复直到完整检查没有发现新问题

**在完成至少一次修复-验证循环之前，不要声明成功。**

---

## 转换为图片

将演示文稿转换为单独的幻灯片图片以便进行可视化检查：

```bash
python scripts/office/soffice.py --headless --convert-to pdf output.pptx
pdftoppm -jpeg -r 150 output.pdf slide
```

这将创建 `slide-01.jpg`、`slide-02.jpg` 等。

修复后重新渲染特定幻灯片：

```bash
pdftoppm -jpeg -r 150 -f N -l N output.pdf slide-fixed
```
