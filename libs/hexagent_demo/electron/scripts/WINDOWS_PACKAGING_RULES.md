# Windows 打包约束与步骤

## 必须遵守的约束
1. 打包入口统一使用 `scripts/build-all.ps1 win`，不要手动跳步骤。
2. 每次打包前必须确认预置镜像路径存在：
   - `libs/hexagent_demo/electron/prebuilt/hexagent-prebuilt.tar`
   - `libs/hexagent_demo/electron/resources/wsl/wsl*.x64.msi`
   - `libs/hexagent_demo/electron/resources/wsl/ubuntu-base-24.04-amd64.tar.gz`
3. 主安装包必须与 `hexagent-prebuilt.tar` 分离分发，不内置到安装器体积中。
4. 卸载时必须清理安装目录内的 `hexagent-prebuilt.tar`。
5. WSL 离线安装包必须与主安装包分离分发（放在安装器同目录）。
6. 打包产物目录必须包含：
   - `UniClaw-Work.exe`
   - `UniClaw-Work.exe.blockmap`
   - `hexagent-prebuilt.tar`
   - `wsl*.x64.msi`
   - `ubuntu-base-24.04-amd64.tar.gz`
   - `安装说明.txt`
   - `UniClaw-工作虾.zip`（统一分发压缩包）

## 标准打包步骤
1. 读取本规则（本文档）并检查关键前置条件。
2. 构建前端。
3. 构建后端（并确保不把 prebuilt tar 打进 backend payload）。
4. 执行 electron-builder 生成 Windows 安装包。
5. 构建结束后检查 `dist`：
   - 若缺少 `hexagent-prebuilt.tar`，从 `electron/prebuilt/` 复制一份。
   - 复制 `resources/wsl` 下离线 WSL 安装资源到 `dist`。
   - 生成或更新 `安装说明.txt`（固定文案）。
   - 将 `UniClaw-Work.exe`、`hexagent-prebuilt.tar`、`wsl*.x64.msi`、`ubuntu-base-24.04-amd64.tar.gz`、`安装说明.txt` 统一压缩为 `UniClaw-工作虾.zip`。

## 验收检查
1. 安装包可生成，且体积在预期范围（通常约 120MB，随版本波动）。
2. `dist` 中存在并可分发：`exe + prebuilt tar + wsl 离线包 + 使用说明 + 压缩包`。
3. 运行时若找到本地离线包，应优先离线安装 WSL 和本地导入 VM；任一步失败后再回退联网安装。
