# Video Factory Frontend

Vue 3 + Vite + TypeScript 管理后台脚手架，目录结构仿照 MyTodo `server/frontend`。

## 开发

```bash
cd frontend
npm install
npm run dev
```

默认开发地址：http://localhost:5175/video_factory/web/

API 地址由 `src/api/config.ts` 自动探测：局域网 nginx 可达时用本地，否则用远程 natapp。

## 构建

```bash
npm run build
```

构建产物输出到 `dist/`，部署路径 base 为 `/video_factory/web/`。

## 目录结构

```
src/
├── api/          # axios 配置 + 业务 API
├── components/   # 通用组件
├── composables/  # 组合式函数
├── constants/    # 常量
├── router/       # 路由
├── stores/       # Pinia 状态
├── styles/       # 全局样式
├── types/        # TypeScript 类型
├── utils/        # 工具函数
└── views/        # 页面（Page*/Tab*/dialogs/）
```
