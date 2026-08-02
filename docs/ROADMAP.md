# 路线图

## 已完成

- React Native Android 项目可运行
- Android SDK/JDK 环境配置完成
- Debug APK 可一键生成
- 首页适老化 UI
- 中文/英文切换
- 按住说话交互 Demo
- 模拟结果展示
- 设计系统与维护文档
- 后端 API 契约与前端 service 骨架（`docs/API.md`、`config/api.json`）

## 下一步建议

### 1. 实现 FastAPI 后端（按契约）

优先级：高

- 按 `docs/API.md` / `docs/openapi.yaml` 实现 Auth / QA / Archives / Family
- 前端改 `config/api.json` 指向后端 IP 后打包联调

### 2. 接入真实语音识别与问答

优先级：高

- 首页替换 mock：调用 `src/services/qaApi.ts`
- 增加失败重试和错误提示

### 3. 增加设置页

优先级：中

- 字体大小设置
- 高对比模式
- 默认语言设置

### 4. 增加历史记录

优先级：中

- 保存最近提问
- 点击历史记录重新查看结果

### 5. 发布准备

优先级：后期

- 配置 release 签名
- 应用图标
- 隐私政策
- 权限说明页面
