# 项目上下文：适老化语音问答手机 App

## 项目目标

本项目是一个面向老年用户的 Android 手机 App 前端项目，使用 React Native 实现。当前阶段优先完成首页 MVP：用户按住大按钮说话，松开后返回结果。

## 用户画像

- 主要用户：老年人
- 关键需求：看得清、点得准、操作步骤少、反馈明确
- 常见限制：视力下降、误触风险高、对复杂导航不熟悉

## 设计原则

1. 大字号：正文默认不低于 18px，主要标题 28px 左右。
2. 大触控区域：核心按钮远大于 48dp，语言切换按钮不小于 44dp。
3. 高对比：主文本使用深色，背景使用暖白色，重要状态使用明确色彩。
4. 简单风格：单屏核心动作，减少复杂菜单与装饰。
5. 中英文支持：仅支持中文和英文，文案集中在 `src/shared/i18n/messages.ts`。
6. 可维护：页面按 feature 组织，设计 token 集中在 `src/theme/tokens.ts`。

## 当前 MVP 功能

- 首页标题与说明
- 中文/英文切换
- 大号“按住说话”按钮
- Android 麦克风权限请求
- 录音状态与处理中状态
- 模拟结果返回
- 结果卡片展示

## 重要说明

当前语音识别还没有接入真实服务，结果来自模拟文案：`mockResult`。后端用 FastAPI 开发时，请按 `docs/API.md` / `docs/openapi.yaml` 实现。

前端已预留 service 层（不要把接口逻辑直接写在 UI 组件里）：

```text
config/api.json              # 改后端 IP 后重新打包
src/config/env.ts
src/services/http.ts
src/services/authApi.ts
src/services/qaApi.ts
src/services/archiveApi.ts
src/services/profileApi.ts
```

## 已配置的本机环境

- Android SDK：`/home/westwell/Android/Sdk`
- JDK 17：`/home/westwell/.local/jdks/jdk17`
- Debug APK 脚本：`scripts/build_android_apk.sh`

## 新对话快速提示

如果换新对话，请告诉助手：

“请先阅读 `docs/PROJECT_CONTEXT.md`、`docs/DESIGN_SYSTEM.md`、`docs/DEVELOPMENT_GUIDE.md`，这是一个 React Native Android 适老化语音问答 App。不要重建项目，基于现有结构开发。”
