# 用户素材处理指南 (Upload Process Mode)

**注意：** 这是一个从零创建 PPT 的优先分支。
如果用户上传了任何参考素材（PDF、图片、文本），**必须优先使用这些素材**，然后执行本指南的处理流程。基于这些素材，后续应当生成包含具体数据的调研报告 `research.md`。

## 素材处理工作流

### 1. 提取文字与图片
使用本 Skill 提供的 `scripts/process_upload.py` 脚本对用户上传的文件进行初步处理。该脚本支持从 PDF 中提取文本和图片，并能归档用户直接上传的图片和文本文档。

```bash
python scripts/process_upload.py --input <用户素材目录> --output <处理后的目标目录>
```
运行后，脚本会在目标目录下生成 `image_xxx.json` 模板文件和对应的 Markdown 文本。

### 2. 视觉分析（🚨 关键安全警告）
提取出图片后，必须为这些图片生成描述，补充到生成的 `image.json` 模板中。

**🚨 严禁直接读取图片：**
Agent 自身**没有任何视觉能力**。**绝对严禁**使用 Read 工具或直接读取任何图片文件，这会导致系统崩溃的严重后果！

**视觉工具使用优先级：**
1. **首选 MCP 视觉工具**：优先使用可用的 MCP 工具批量读取目标目录中的图片，并让其描述图片内容。
2. **备选 Python 脚本**：只有在 MCP 无法完成视觉任务时，才使用本 Skill 提供的脚本进行处理：
   ```bash
   python scripts/vision_qwen.py --images <图片1路径> <图片2路径> ...
   ```

### 3. 补充和规范 `image.json`
根据视觉工具返回的描述，更新或生成对应的 `image.json` 文件。请确保 JSON 格式如下：

```json
[
  {
    "local_rel_path": "image/example.png",
    "description": "这是一张柱状图，展示了2023年各季度的销售额增长趋势..."
  },
  {
    "local_rel_path": "image/document/p1_i1.png",
    "description": "公司Logo标志，包含蓝色和白色的几何图形..."
  }
]
```

### 4. 生成报告
素材处理完毕（文本已提取，图片已有描述）后，综合这些内容生成一份具有具体数据的调研报告 `research.md`，为后续大纲的生成做好准备。
