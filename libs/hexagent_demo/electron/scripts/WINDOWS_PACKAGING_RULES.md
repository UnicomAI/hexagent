# Windows 打包约束与步骤

## 必须遵守的约束
1. 打包入口统一使用 `scripts/build-all.ps1 win`，不要手动跳步骤。
2. 每次打包前必须确认预置镜像路径存在：
   - `libs/hexagent_demo/electron/prebuilt/hexagent-prebuilt.tar`
3. 主安装包必须与 `hexagent-prebuilt.tar` 分离分发，不内置到安装器体积中。
4. 卸载时必须清理安装目录内的 `hexagent-prebuilt.tar`。
5. 打包产物目录必须包含：
   - `*.exe`
   - `*.exe.blockmap`
   - `hexagent-prebuilt.tar`
   - `INSTALL-WINDOWS.txt`

## 标准打包步骤
1. 读取本规则（本文件）并检查关键前置条件。
2. 构建前端。
3. 构建后端（并确保不把 prebuilt tar 打进 backend payload）。
4. 执行 electron-builder 生成 Windows 安装包。
5. 构建结束后检查 `dist`：
   - 若缺少 `hexagent-prebuilt.tar`，从 `electron/prebuilt/` 复制一份。
   - 生成或更新 `INSTALL-WINDOWS.txt`（中文说明）。

## 验收检查
1. 安装包可生成，且体积在预期范围（约 120MB 左右，随版本波动）。
2. `dist` 中存在并可分发：`exe + blockmap + prebuilt tar + 安装说明`。
3. 运行时若找到 `hexagent-prebuilt.tar`，应优先本地导入；找不到则回退联网安装。
