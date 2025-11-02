

# iFaceOff - AI 模拟面试平台

**iFaceOff** 是一个功能强大的全栈 AI 模拟面试平台，旨在通过先进的人工智能技术，为求职者提供一个集**练习、反馈、学习**于一体的个人求职赋能中心。

![img](https://private-user-images.githubusercontent.com/167274430/502959840-3afa115b-203f-411a-95ca-df95fc5f4e87.png?jwt=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJpc3MiOiJnaXRodWIuY29tIiwiYXVkIjoicmF3LmdpdGh1YnVzZXJjb250ZW50LmNvbSIsImtleSI6ImtleTUiLCJleHAiOjE3NjIwNzk0ODgsIm5iZiI6MTc2MjA3OTE4OCwicGF0aCI6Ii8xNjcyNzQ0MzAvNTAyOTU5ODQwLTNhZmExMTViLTIwM2YtNDExYS05NWNhLWRmOTVmYzVmNGU4Ny5wbmc_WC1BbXotQWxnb3JpdGhtPUFXUzQtSE1BQy1TSEEyNTYmWC1BbXotQ3JlZGVudGlhbD1BS0lBVkNPRFlMU0E1M1BRSzRaQSUyRjIwMjUxMTAyJTJGdXMtZWFzdC0xJTJGczMlMkZhd3M0X3JlcXVlc3QmWC1BbXotRGF0ZT0yMDI1MTEwMlQxMDI2MjhaJlgtQW16LUV4cGlyZXM9MzAwJlgtQW16LVNpZ25hdHVyZT0yNDdmYWQ5YTdmZjMzZDNjMDFiNTQ5Y2I3Y2E3ZTViYWNmYzkwZGU5MGMzZTRkMzZkMDRjZTdjOGI1ZGY4NDEyJlgtQW16LVNpZ25lZEhlYWRlcnM9aG9zdCJ9.66FudoxsYw-pyEt-_mm1TQXwITiSW8MGw8S4wZUjQFA)

---

## ✨ 核心功能

*   **🤖 AI 模拟面试**: 用户可选择目标岗位，与 AI 进行多轮语音或文字面试，体验真实面试流程。
*   **📊 实时多维度分析**: 在面试过程中，系统通过摄像头和麦克风实时分析用户的**面部情绪**和**语音语调**。
*   **📝 深度面试报告**: 面试结束后，自动生成包含能力雷达图、情绪波动分析、关键词匹配、STAR 法则应用情况等全方位的综合评估报告。
*   **📄 简历中心**:
    *   强大的在线简历编辑器，支持模块化拖拽和多模板切换。
    *   AI 简历诊断，上传简历与 JD (岗位描述) 进行匹配度分析和优化建议。
    *   AI 一键生成简历初稿。
*   **✍️ 内容社区 (博客)**: 一个功能完善的内容创作与分享平台，支持 Markdown、代码高亮、数学公式、Mermaid 图表和丰富的发布选项。
*   **📈 个人文章管理**: 提供数据分析仪表盘，包含总览数据和每日数据趋势图表，帮助创作者追踪内容表现。

## 🚀 技术栈

本项目采用前后端分离架构。

#### **前端 (ai-interview-frontend)**

*   **核心框架**: Vue 3 (Composition API) + Vite
*   **编程语言**: TypeScript
*   **状态管理**: Pinia
*   **路由**: Vue Router
*   **UI 组件库**: Element Plus
*   **Markdown 编辑器**: md-editor-v3
*   **HTTP 请求**: Axios

#### **后端 (ai-interview-backend)**

*   **核心框架**: Django + Django REST Framework (DRF)
*   **编程语言**: Python
*   **数据库**: MySQL
*   **异步任务队列**: Celery + Redis
*   **缓存**: Redis
*   **认证**: Simple JWT + Django Allauth (用于第三方登录)
*   **AI 服务**: OpenAI SDK

---

## 🔧 环境准备 (Prerequisites)

在开始之前，请确保您的开发环境中已安装以下软件：

*   **Node.js**: `v18.x` 或更高版本
*   **Python**: `v3.10` 或更高版本
*   **MySQL**: `v8.0` 或更高版本
*   **Redis**: `v6.x` 或更高版本
*   **Git**

---

## ⚙️ 安装与启动 (Installation & Setup)

请按照以下步骤在您的本地环境中部署和运行本项目。

### **1. 克隆项目**

```bash
git clone https://github.com/6Asmile/AI_interview.git
cd AI_interview
```

### **2. 后端 (ai-interview-backend) 启动步骤**

1. **进入后端目录**

   ```bash
   cd ai-interview-backend
   ```

2. **创建并激活 Python 虚拟环境**

   * **Windows**:

     ```bash
     python -m venv .venv
     .venv\Scripts\activate
     ```

   * **macOS / Linux**:

     ```bash
     python3 -m venv .venv
     source .venv/bin/activate
     ```

3. **安装依赖**
   *在后端目录下创建一个 `requirements.txt` 文件，并填入以下内容：*

   ```txt
   Django
   djangorestframework
   django-cors-headers
   mysqlclient
   celery
   redis
   django-redis
   python-dotenv
   openai
   pypdf
   python-docx
   djangorestframework-simplejwt
   dj-rest-auth
   django-allauth
   drf-nested-routers
   ```

   *然后运行安装命令：*

   ```bash
   pip install -r requirements.txt
   ```

4. **配置环境变量**
   *在 `ai-interview-backend` 目录下，创建一个 `.env` 文件，并根据您的本地环境填入以下内容：*

   ```env
   # 数据库配置
   DB_NAME=your_db_name
   DB_USER=your_db_user
   DB_PASSWORD=your_db_password
   DB_HOST=127.0.0.1
   DB_PORT=3306
   
   # 邮箱配置 (用于发送注册验证码)
   EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
   EMAIL_HOST=smtp.qq.com
   EMAIL_PORT=587
   EMAIL_HOST_USER=your_email@qq.com
   EMAIL_HOST_PASSWORD=your_email_smtp_password # 注意：这不是邮箱密码，而是SMTP服务的授权码
   EMAIL_USE_TLS=True
   
   ```

5. **数据库配置**

   * 请在您的 MySQL 中**手动创建一个数据库**，名称与 `.env` 文件中的 `DB_NAME` 一致。

   * 执行数据库迁移：

     ```bash
     python manage.py makemigrations
     python manage.py migrate
     ```

6. **启动后端服务**

   * **启动 Django 主服务** (需要一个终端):

     ```bash
     python manage.py runserver
     ```

   * **启动 Celery Worker** (需要第二个终端):

     ```bash
     celery -A ai_interview_backend worker -l info -P gevent
     ```

   * **启动 Celery Beat (定时任务)** (需要第三个终端):

     ```bash
     celery -A ai_interview_backend beat -l info
     ```

   > ✅ 此时，您的后端服务应该已经在 `http://127.0.0.1:8000` 运行。

### **3. 前端 (ai-interview-frontend) 启动步骤**

1. **进入前端目录**

   ```bash
   cd ai-interview-frontend
   ```

2. **安装依赖**

   ```bash
   npm install
   ```

3. **配置环境变量**
   *在 `ai-interview-frontend` 目录下，创建一个 `.env.development` 文件，并填入以下内容：*

   ```env
   # 后端 API 的基础 URL
   VITE_API_BASE_URL=http://127.0.0.1:8000/api/v1
   ```

4. **启动前端开发服务器**

   * (需要第四个终端)

     ```bash
     npm run dev
     ```

   > ✅ 此时，您的前端应用应该已经在 `http://localhost:5173` (或终端提示的其他端口) 运行，并且可以与后端正常通信。

---

现在，您已经成功在本地部署了 iFaceOff 平台！🎉
