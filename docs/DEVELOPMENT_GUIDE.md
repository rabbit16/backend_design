# 开发维护指南

## 常用命令

进入项目目录：

```bash
cd /home/westwell/haolliang.jiang/westwellDoc/app/senior_voice_app
```

检查环境：

```bash
npm run doctor:android
```

启动 Metro：

```bash
npm start
```

连接真机后运行：

```bash
./scripts/run_android_device.sh
```

生成 Debug APK：

```bash
npm run build:android
```

APK 输出：

```text
android/app/build/outputs/apk/debug/app-debug.apk
```

代码检查：

```bash
npm run check
```

## 目录结构

```text
config/
  api.json                 # 打包前改后端 IP
  api.example.json
src/
  config/
    env.ts                 # 读取 api.json
  features/
    auth/
    archive/
    home/
    profile/
  navigation/
  services/                # 后端 API 调用层
    http.ts
    authApi.ts
    qaApi.ts
    archiveApi.ts
    profileApi.ts
  shared/
    i18n/
      messages.ts
  theme/
    tokens.ts
scripts/
  build_android_apk.sh
  check_android_env.sh
  run_android_device.sh
docs/
  API.md                   # RESTful 接口说明
  openapi.yaml             # OpenAPI 契约（给 FastAPI）
  PROJECT_CONTEXT.md
  DESIGN_SYSTEM.md
  DEVELOPMENT_GUIDE.md
  ROADMAP.md
```

## 如何改后端 IP 后打包

1. 编辑 `config/api.json` 的 `apiBaseUrl`（真机不要用 localhost，用电脑局域网 IP）：

```json
{
  "apiBaseUrl": "http://10.0.0.8:8000",
  "apiPrefix": "/api/v1",
  "timeoutMs": 30000
}
```

2. 打包：

```bash
npm run build:android
```

也可不改文件，临时覆盖：

```bash
API_BASE_URL=http://10.0.0.8:8000 npm run build:android
```

接口契约见：`docs/API.md`、`docs/openapi.yaml`。

## 如何改界面

1. 优先改 `src/features/home/HomeScreen.tsx`。
2. 如果是复用组件，改 `src/features/home/components/`。
3. 如果是颜色/字号/间距，改 `src/theme/tokens.ts`。
4. 如果是中文/英文文案，改 `src/shared/i18n/messages.ts`。
5. 改完后运行：

```bash
npm run check
npm run build:android
```

## 如何接入真实语音识别

首页当前仍是 mock。接入时调用：

```ts
import {recognizeSpeech, askQuestion} from '../../services/qaApi';
```

不要直接在 HomeScreen 中写 `fetch` 细节，统一走 `src/services/*`。

## 如何接入真实问答接口

见 `docs/API.md`。典型流程：

1. `POST /voice/recognize` 得到文本
2. `POST /qa/sessions` 得到回答
3. 可选：`POST /qa/sessions/{id}/recommendations` 得到就医建议

## 不建议做的事

- 不要在每个组件里随意写颜色值。
- 不要把复杂接口逻辑写进 UI 组件。
- 不要缩小核心按钮尺寸。
- 不要删除无障碍标签。
- 不要为了好看加入复杂动画。
