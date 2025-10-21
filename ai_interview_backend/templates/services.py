from docx import Document
from docx.shared import Inches
import uuid


def parse_docx_to_json(file_path: str) -> dict:
    """
    一个【简化版】的 Word (.docx) 解析器。
    它会尝试将 Word 文档的结构转换为前端简历编辑器可识别的 JSON 格式。
    注意：这是一个非常基础的实现，实际应用中需要根据您的 Word 模板结构进行深度定制。
    """
    document = Document(file_path)

    layout = {
        "sidebar": [],
        "main": []
    }

    # 假设 Word 模板使用一级标题来区分不同的简历模块
    # 例如："基本信息", "教育背景", "工作经历" 等

    current_module = None

    for para in document.paragraphs:
        # 检查是否为一级标题，这通常是新模块的开始
        if para.style.name.startswith('Heading 1'):
            title = para.text.strip()

            # 根据标题猜测模块类型 (这是一个简化的映射，可以做得更复杂)
            module_type_map = {
                "基本信息": "BaseInfo",
                "教育背景": "Education",
                "工作经历": "WorkExp",
                "项目经历": "Project",
                "专业技能": "Skills",
                "自我评价": "Summary",
            }
            module_type = module_type_map.get(title, "Custom")  # 默认为自定义模块

            # 创建新的模块对象
            current_module = {
                "id": str(uuid.uuid4()),
                "componentName": f"{module_type}Module",
                "moduleType": module_type,
                "title": title,
                "props": {"show": True, "title": title}
            }

            # 一个简化的布局逻辑：基本信息和技能放侧边栏
            if module_type in ["BaseInfo", "Skills"]:
                layout["sidebar"].append(current_module)
            else:
                layout["main"].append(current_module)

        # 如果当前在一个模块内，处理段落内容
        elif current_module:
            text = para.text.strip()
            if not text:
                continue

            # 根据模块类型，将文本填充到 props 的不同字段
            # 这是最需要定制的部分
            if current_module["moduleType"] == "Summary":
                current_module["props"]["summary"] = current_module["props"].get("summary", "") + text + "\n"

            elif current_module["moduleType"] == "WorkExp":
                if "experiences" not in current_module["props"]:
                    current_module["props"]["experiences"] = []
                # 简化处理：每个非空段落都作为新经历的描述
                current_module["props"]["experiences"].append({
                    "id": str(uuid.uuid4()),
                    "company": "公司名称", "position": "职位", "dateRange": [None, None],
                    "description": text
                })

            # ... 在这里添加对其他模块类型 (Education, Project 等) 的解析逻辑 ...

            else:  # 自定义模块
                current_module["props"]["content"] = current_module["props"].get("content", "") + text + "\n"

    return layout