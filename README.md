# IFaceOff - AI 模拟面试平台

<img width="1920" height="1109" alt="image" src="https://github.com/user-attachments/assets/3afa115b-203f-411a-95ca-df95fc5f4e87" />


**IFaceOff** 是一款功能强大的智能化模拟面试平台，旨在通过前沿的人工智能技术，为求职者提供一个高度仿真、可随时随地进行、并能获得深度反馈的面试训练环境。

---

## ✨ 项目亮点 (Features)

*   **🤖 智能 AI 面试官**: 基于强大的大语言模型 (LLM)，能够根据用户选择的岗位和上传的简历，进行有针对性的、多轮的追问式面试。
*   **🚀 实时流式反馈**: 在回答完每一个问题后，即刻获得 AI 对该问题的简评，并通过流式输出 (Streaming) 平滑地呈现下一个问题，打造沉浸式交互体验。
*   **🎨 高度可定制的在线简历编辑器**:
    *   **所见即所得**: 提供“左侧配置、右侧预览”的专业编辑模式。
    *   **自由布局**: 支持丰富的模块库，用户可通过拖拽自由组合、排序，并支持“左右分栏”等多种专业布局。
    *   **多模板切换**: 内置多套设计精美的简历模板，支持一键切换，瞬间改变简历风格。
*   **🧠 AI 赋能简历优化**:
    *   **一键润色**: 对工作经历、项目描述等关键内容，一键调用 AI 进行 STAR 法则优化，并提供差异化对比。
    *   **JD 匹配度分析**: 上传目标岗位的职位描述 (JD)，AI 将深度分析简历与 JD 的匹配度，返回包含量化得分、关键词分析、优劣势和具体修改建议的结构化报告。
*   **📈 多维度面试报告**: 面试结束后，自动生成一份包含综合评分、能力维度雷达图、情绪分析、关键词分析、STAR 法则评估和逐题回顾的综合性复盘报告。
*   **中断恢复与历史追溯**: 支持面试中断后无缝恢复，所有面试记录和分析报告都将被永久保存，方便用户随时回顾和追踪成长。

---

## 🛠️ 技术栈 (Tech Stack)

本项目采用现代化的前后端分离架构。

### **前端 (ai-interview-frontend)**

*   **框架**: Vue 3 (Composition API) + TypeScript
*   **构建工具**: Vite
*   **状态管理**: Pinia
*   **UI 组件库**: Element Plus
*   **样式**: TailwindCSS
*   **路由**: Vue Router
*   **核心交互**:
    *   `vuedraggable`: 实现简历编辑器的自由拖拽布局。
    *   `@wangeditor/editor-for-vue`: 提供富文本编辑能力。
    *   `html2canvas` & `jspdf`: 实现简历/报告的 PDF 导出。
    *   `face-api.js`: （已集成）用于实时面部情绪识别。
    *   `ECharts`: 用于数据可视化。

### **后端 (ai-interview-backend)**

*   **框架**: Django + Django REST Framework (DRF)
*   **AI 集成**: OpenAI SDK (兼容 DeepSeek 等多种模型)
*   **数据库**: MySQL
*   **缓存**: Redis (用于缓存中断的面试会话等)
*   **异步任务**: Celery + Celery Beat (用于处理超时的“僵尸”面试)
*   **认证**: `dj-rest-auth` + `django-allauth` + `Simple JWT` (支持邮箱注册和 GitHub OAuth 2.0)

---

## 🚀 快速开始 (Getting Started)

### **环境准备**

*   Node.js (v18+ 推荐)
*   Python (v3.10+ 推荐)
*   MySQL (v8.0+ 推荐)
*   Redis

### **后端 (`ai-interview-backend`) 启动流程**

1.  **克隆项目**:
    ```bash
    git clone https://github.com/6Asmile/AI_interview.git
    cd AI_interview/ai-interview-backend
    ```
2.  **创建并激活虚拟环境**:
    ```bash
    python -m venv venv
    # Windows
    .\venv\Scripts\activate
    # macOS / Linux
    source venv/bin/activate
    ```
3.  **安装依赖**:
    ```bash
    pip install -r requirements.txt
    ```
4.  **配置环境变量**:
    *   复制 `.env.example` 文件并重命名为 `.env`。
    *   根据您的本地环境，修改 `.env` 文件中的数据库配置 (`DB_*`) 和 AI 模型的 API Key (`DEEPSEEK_API_KEY`)。
5.  **数据库迁移**:
    ```bash
    python manage.py makemigrations
    python manage.py migrate
    ```
6.  **创建超级用户** (用于访问Admin后台):
    ```bash
    python manage.py createsuperuser
    ```
7.  **启动服务**:
    *   **Django 开发服务器**:
        ```bash
        python manage.py runserver
        ```
    *   **Celery Worker** (在**新**终端中):
        ```bash
        celery -A ai_interview_backend worker -l info
        ```
    *   **Celery Beat 调度器** (在**再一个新**终端中):
        ```bash
        celery -A ai_interview_backend beat -l info
        ```
    后端现在运行在 `http://127.0.0.1:8000`。

### **前端 (`ai-interview-frontend`) 启动流程**

1.  **进入前端目录**:
    ```bash
    cd ../ai-interview-frontend 
    ```
2.  **安装依赖**:
    ```bash
    npm install
    ```
3.  **配置环境变量**:
    *   在根目录下创建一个 `.env.development` 文件。
    *   添加后端 API 的地址：
        ```
        VITE_API_BASE_URL=http://127.0.0.1:8000/api/v1
        ```
4.  **启动服务**:
    ```bash
    npm run dev
    ```
    前端现在运行在 `http://localhost:5173`。

---

## 📸 项目截图 (Screenshots)

*(建议在此处放置几张最能代表您项目核心功能的截图)*

| 在线简历编辑器 | AI 简历分析报告 |
| :---: | :---: |
<img width="1920" height="1198" alt="image" src="https://github.com/user-attachments/assets/049d4286-7497-417c-ac6a-b089521aeeaa" />
<img width="1911" height="1115" alt="image" src="https://github.com/user-attachments/assets/b8ee0df9-75b5-4f4c-b39b-eba07266675f" />
<img width="1915" height="1101" alt="image" src="https://github.com/user-attachments/assets/830eaae3-710f-4e33-9b25-779b016aa19e" />




| AI 模拟面试 | 面试复盘报告 |
| :---: | :---: |
<img width="1920" height="1110" alt="image" src="https://github.com/user-attachments/assets/540b8bc0-03f3-4ceb-bb8b-30baaa367c88" />
<img width="1920" height="1198" alt="image" src="https://github.com/user-attachments/assets/daf54d79-a91e-4302-bf13-fc06dff9e794" />
<img width="650" height="1074" alt="image" src="https://github.com/user-attachments/assets/3b005d86-1a6b-42bc-b882-5ee26e744d6d" />
<img width="640" height="1016" alt="image" src="https://github.com/user-attachments/assets/2df3d81d-7c8c-4ef6-852b-3cdb9eeb3d7f" />







---

## 🗺️ 未来规划 (Roadmap)

我们致力于将 IFaceOff 打造成一个全方位的求职赋能平台。

*   [ ] **AI 润色 Pro**: 增加差异化对比视图和多风格选择。
*   [ ] **专业模块增强**: 为“技能”模块增加可视化熟练度展示（进度条/星级）。
*   [ ] **账户管理**: 实现“默认简历”设置和“复制简历”功能。
*   [ ] **企业端功能**: 开发 HR 端题库管理和面试管理功能。
*   [ ] **移动端适配**: 优化在移动设备上的访问体验。

---

## 🙏 致谢 (Acknowledgements)

*   感谢所有为本项目提供灵感的开源项目。
*   感谢所有使用的第三方库的开发者。

---

## 📜 许可证 (License)

本项目采用 [MIT License](LICENSE)。

### **使用说明和建议**

1.  **Banner 和截图**:
    *   `![IFaceOff-Banner](...)` 和表格中的截图部分，我使用了占位符 URL。强烈建议您**替换**为您自己制作的项目 Banner 和实际的项目截图。您可以将图片上传到 GitHub Issue 中，然后复制其 URL，这是一种常用的图床方法。
2.  **`.env.example`**:
    *   请在后端目录 `ai-interview-backend/` 中创建一个 `.env.example` 文件，将 `.env` 文件中的**所有键**复制进去，但**不要包含值**。例如：
        ```
        DB_NAME=
        DB_USER=
        DB_PASSWORD=
        DB_HOST=
        DB_PORT=
        DEEPSEEK_API_KEY=
        ```
    *   这可以告诉其他开发者项目需要哪些环境变量。
3.  **`requirements.txt`**:
    *   请确保后端目录 `ai-interview-backend/` 中有一个 `requirements.txt` 文件，它包含了所有 Python 依赖。您可以在虚拟环境中运行以下命令生成它：
        ```bash
        pip freeze > requirements.txt
        ```
4.  **许可证**:
    *   我在末尾提到了 `MIT License`。如果您决定使用这个许可证，请在项目根目录下创建一个名为 `LICENSE` 的文件，并将 MIT 许可证的文本内容复制进去。

这份 README 应该能很好地展示您项目的全貌和专业性。祝贺您项目达到了一个新的里程碑！
