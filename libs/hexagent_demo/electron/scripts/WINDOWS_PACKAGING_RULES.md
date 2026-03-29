# Windows 打包约束与步骤

## 必须遵守的约束
1. 打包入口统一使用 `scripts/build-all.ps1 win`，不要手动跳步骤。
2. 每次打包前必须确认预置镜像路径存在：
   - `libs/hexagent_demo/electron/prebuilt/hexagent-prebuilt.tar`
3. 主安装包必须与 `hexagent-prebuilt.tar` 分离分发，不内置到安装器体积中。
4. 卸载时必须清理安装目录内的 `hexagent-prebuilt.tar`。
5. 打包产物目录必须包含：
   - `UniClaw-Work.exe`
   - `UniClaw-Work.exe.blockmap`
   - `hexagent-prebuilt.tar`
   - `UniClaw-Work使用说明.txt`
   - `UniClaw-工作虾.zip`（统一分发压缩包）

## 标准打包步骤
1. 读取本规则（本文档）并检查关键前置条件。
2. 构建前端。
3. 构建后端（并确保不把 prebuilt tar 打进 backend payload）。
4. 执行 electron-builder 生成 Windows 安装包。
5. 构建结束后检查 `dist`：
   - 若缺少 `hexagent-prebuilt.tar`，从 `electron/prebuilt/` 复制一份。
   - 生成或更新 `UniClaw-Work使用说明.txt`（中文说明）。
   - 将 `UniClaw-Work.exe`、`hexagent-prebuilt.tar`、`UniClaw-Work使用说明.txt` 统一压缩为 `UniClaw-工作虾.zip`。

## 验收检查
1. 安装包可生成，且体积在预期范围（通常约 120MB，随版本波动）。
2. `dist` 中存在并可分发：`exe + prebuilt tar + 使用说明 + 压缩包`。
3. 运行时若找到 `hexagent-prebuilt.tar`，应优先本地导入；找不到则回退联网安装。
