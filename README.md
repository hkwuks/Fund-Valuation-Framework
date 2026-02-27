# 基金估值系统

一个基于FastAPI和TypeScript的基金估值可视化系统，通过实时获取股票、基金、指数价格来计算基金的估算净值。

## 功能特性

- 基金管理：添加、查看、删除基金
- 持仓管理：管理基金的持仓明细
- 实时行情：集成多个数据源获取实时价格
- 估值计算：基于持仓实时价格计算基金估算净值
- 可视化展示：直观展示基金信息和估值结果

## 技术栈

### 后端
- FastAPI：高性能Web框架
- Pydantic：数据验证
- AkShare：中国金融数据接口
- yFinance：Yahoo Finance数据接口

### 前端
- TypeScript：类型安全的JavaScript
- Vite：现代前端构建工具
- 原生JavaScript：无复杂框架依赖

## 安装和运行

### 后端

1. 创建conda环境并安装依赖：
```bash
conda activate torch
pip install -r requirements.txt
```

2. 启动后端服务：
```bash
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

### 前端

1. 安装依赖：
```bash
cd frontend
npm install
```

2. 启动开发服务器：
```bash
npm run dev
```

3. 构建生产版本：
```bash
npm run build
```

## 使用说明

1. 访问 http://localhost:3000 打开前端界面
2. 点击"添加基金"按钮创建新基金
3. 在基金详情中添加持仓明细
4. 点击"计算估值"获取实时估值结果

## 数据源

系统支持以下数据源：
- AkShare：中国股票、基金、指数数据
- yFinance：国际市场数据
- 可扩展其他数据源

## API文档

启动后端后访问 http://localhost:8000/docs 查看完整的API文档。

## 项目结构

```
基金估值/
├── backend/              # 后端代码
│   ├── api/             # API路由
│   ├── config.py        # 配置
│   ├── models.py        # 数据模型
│   ├── fund_service.py  # 基金服务
│   └── market_data.py   # 市场数据服务
├── frontend/            # 前端代码
│   ├── src/
│   │   ├── api.ts       # API客户端
│   │   ├── app.ts       # 应用主逻辑
│   │   ├── fundManager.ts # 基金管理器
│   │   ├── renderer.ts  # 渲染器
│   │   ├── types.ts     # 类型定义
│   │   ├── utils.ts     # 工具函数
│   │   └── style.css    # 样式
│   └── index.html       # 入口文件
├── data/                # 数据存储目录
└── requirements.txt     # Python依赖
```
