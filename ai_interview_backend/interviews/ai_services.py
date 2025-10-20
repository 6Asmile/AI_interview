# ai_interview_backend/interviews/ai_services.py

import os
import json
from openai import OpenAI
from dotenv import load_dotenv
from users.models import User
from system.models import AISetting, AIModel

load_dotenv()
SYSTEM_DEFAULT_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEFAULT_MODEL_SLUG = "deepseek-chat"


def _get_user_ai_config(user: User) -> tuple[str | None, AIModel | None]:
    """
    【新版】获取用户的AI配置。
    1. 确定要使用的模型 (用户默认 -> 系统默认)。
    2. 根据确定的模型，查找对应的API Key (用户自定义Key -> 系统默认Key)。
    返回 (api_key, model_object)
    """
    user_setting = None
    try:
        user_setting = user.ai_setting
    except AISetting.DoesNotExist:
        print(f"用户 {user.username} 没有任何AI设置。")

    # --- 步骤1: 确定模型 ---
    final_model = None
    if user_setting and user_setting.ai_model:
        final_model = user_setting.ai_model
        print(f"用户 {user.username} 已选择默认模型: {final_model.name}")

    if not final_model:
        try:
            final_model = AIModel.objects.get(model_slug=DEFAULT_MODEL_SLUG, is_active=True)
            print(f"用户未设置默认模型，回退到系统默认模型: {final_model.name}")
        except AIModel.DoesNotExist:
            print(f"警告: 系统默认模型 slug '{DEFAULT_MODEL_SLUG}' 在数据库中不存在！")
            return SYSTEM_DEFAULT_API_KEY, None  # 返回 None 表示模型查找失败

    # --- 步骤2: 根据确定的模型查找 API Key ---
    api_key = None
    if user_setting and user_setting.api_keys:
        model_id_str = str(final_model.id)
        api_key = user_setting.api_keys.get(model_id_str)
        if api_key:
            print(f"找到并使用用户为模型 '{final_model.name}' 自定义的 API Key。")

    if not api_key:
        print(f"用户未提供该模型的 Key，回退到系统默认 API Key。")
        api_key = SYSTEM_DEFAULT_API_KEY

    return api_key, final_model


def _call_openai_api(api_key: str, model: AIModel, messages: list, max_tokens: int, temperature: float):
    """
    一个统一调用 OpenAI API 的辅助函数，现在能智能处理 JSON Mode。
    """
    client = OpenAI(api_key=api_key, base_url=model.base_url)

    request_params = {
        "model": model.model_slug,
        "messages": messages,
        "stream": False,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }

    if model.supports_json_mode:
        request_params["response_format"] = {"type": "json_object"}
        print(f"为模型 '{model.name}' 启用 JSON Mode。")
    else:
        print(f"模型 '{model.name}' 不支持 JSON Mode，将进行常规调用。")

    response = client.chat.completions.create(**request_params)
    content = response.choices[0].message.content

    if not model.supports_json_mode:
        # 清理可能存在的代码块标记
        content = content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

    return json.loads(content)


def _call_openai_api_stream(api_key: str, model: AIModel, messages: list, max_tokens: int, temperature: float):
    client = OpenAI(api_key=api_key, base_url=model.base_url)
    stream = client.chat.completions.create(
        model=model.model_slug,
        messages=messages,
        stream=True,
        max_tokens=max_tokens,
        temperature=temperature
    )
    for chunk in stream:
        content = chunk.choices[0].delta.content or ""
        yield content


# --- 【核心修复】更新所有 AI 服务函数以使用新的 _get_user_ai_config 签名 ---

def generate_first_question(job_position: str, user: User, resume_text: str = None) -> str:
    api_key, model = _get_user_ai_config(user)
    if not api_key or not model:
        return "系统AI服务未配置或模型不存在。"

    system_prompt = (
        "你是一位顶尖公司的资深技术面试官，以提问精准、深入、专业著称。"
        "你的任务是开启一场关于特定岗位的面试。"
    )
    if resume_text:
        user_prompt = (
            f"我正在应聘 '{job_position}' 岗位。这是我的简历内容：\n\n"
            f"--- 简历开始 ---\n{resume_text}\n--- 简历结束 ---\n\n"
            "请仔细阅读我的简历，并提出一个有针对性的开场问题。"
            "请严格按照以下 JSON 格式返回，只包含问题文本：\n"
            "{\"question\": \"(你的问题在这里)\"}"
        )
    else:
        user_prompt = (
            f"我正在应聘 '{job_position}' 岗位，但未提供简历。"
            "请为我生成一个通用但热情的开场问题，要求我进行一个简洁的自我介绍。"
            "请严格按照以下 JSON 格式返回，只包含问题文本：\n"
            "{\"question\": \"(你的问题在这里)\"}"
        )

    try:
        messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]
        ai_response = _call_openai_api(api_key, model, messages, 300, 0.7)
        return ai_response.get("question", "你好，请做个自我介绍吧。")
    except Exception as e:
        print(f"调用 AI 生成第一问时发生错误: {e}")
        return f"你好，欢迎参加 {job_position} 的面试。很抱歉，我的AI大脑暂时出了一点小问题。不过没关系，我们可以从一个经典问题开始：请先做一个简单的自我介绍吧。"


def analyze_answer(job_position: str, question: str, answer: str, user: User) -> str:
    api_key, model = _get_user_ai_config(user)
    if not api_key or not model:
        return "AI服务未配置，无法生成简评。"

    system_prompt = "你是一位专业的面试官，任务是根据候选人的回答给出一个简短、有建设性的评价。"
    user_prompt = (
        f"我正在面试 '{job_position}' 岗位。\n"
        f"面试官提问: {question}\n"
        f"我的回答: {answer}\n\n"
        "请对我的回答给出一个大约50-100字的简评。直接返回评价本身，不要包含多余内容。"
    )
    try:
        # 这个函数比较简单，可以直接调用 OpenAI API
        client = OpenAI(api_key=api_key, base_url=model.base_url)
        response = client.chat.completions.create(
            model=model.model_slug,
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            stream=False,
            max_tokens=200,
            temperature=0.6
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"调用 AI 生成简评时发生错误: {e}")
        return "AI 在分析时遇到了一点小问题。"


def generate_next_question_stream(job_position: str, interview_history: list, user: User):
    api_key, model = _get_user_ai_config(user)
    if not api_key or not model:
        yield "AI服务未配置。"
        return

    history_prompt_part = ""
    for turn in interview_history:
        history_prompt_part += f"面试官: {turn['question']}\n我: {turn['answer']}\n\n"
    system_prompt = "你是一位专业的AI面试官，任务是根据对话历史提出下一个有深度的追问。直接返回问题本身。"
    user_prompt = f"这是关于 '{job_position}' 的面试历史:\n{history_prompt_part}\n现在，请提出你的下一个问题。"

    try:
        messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]
        yield from _call_openai_api_stream(api_key, model, messages, 500, 0.8)
    except Exception as e:
        print(f"调用 AI 生成下一问时发生错误: {e}")
        yield "请谈谈你遇到的最大的技术挑战是什么？"


def generate_final_report(job_position: str, interview_history: list, user: User) -> dict:
    api_key, model = _get_user_ai_config(user)
    if not api_key or not model:
        return {"error": "AI服务未配置，无法生成报告。"}

    history_prompt_part = ""
    for i, turn in enumerate(interview_history):
        history_prompt_part += f"--- 问题 {i + 1} ---\n"
        history_prompt_part += f"面试官提问: {turn['question']}\n"
        history_prompt_part += f"我的回答: {turn['answer']}\n\n"

    system_prompt = (
        "你是一位顶级的职业规划师和面试分析专家，尤其擅长使用 STAR 法则优化工作和项目描述以及结构化思维分析和关键词提取。"
        "你的任务是基于一场完整的面试记录，生成一份专业、数据驱动、富有洞察力的面试报告。"
    )
    user_prompt = (
        f"我刚刚完成了一场关于 '{job_position}' 岗位的模拟面试。完整的问答记录如下：\n\n"
        f"--- 面试记录开始 ---\n{history_prompt_part}--- 面试记录结束 ---\n\n"
        "请对我本次面试进行综合评估，并严格按照下面的 JSON 格式返回你的分析报告。"
        "所有评分都是0-5分，可以有1位小数。所有文本内容需客观、专业且有建设性。\n"
        "{\n"
        "  \"overall_score\": \"(一个0到100的整数，代表综合得分)\",\n"
        "  \"ability_scores\": [\n"
        "    {\"name\": \"专业知识\", \"score\": (0-5分)},\n"
        "    {\"name\": \"项目经验\", \"score\": (0-5分)},\n"
        "    {\"name\": \"逻辑思维\", \"score\": (0-5分)},\n"
        "    {\"name\": \"沟通表达\", \"score\": (0-5分)},\n"
        "    {\"name\": \"求职动机\", \"score\": (0-5分)}\n"
        "  ],\n"
        "  \"overall_comment\": \"(一段100字左右的总体评价)\",\n"
        "  \"strength_analysis\": \"(关于本次面试亮点的分析)\",\n"
        "  \"weakness_analysis\": \"(关于本次面试不足之处的分析)\",\n"
        "  \"improvement_suggestions\": [\n"
        "    \"(第一条具体的改进建议)\",\n"
        "    \"(第二条具体的改进建议)\"\n"
        "  ],\n"
        "  \"keyword_analysis\": {\n"
        "    \"matched_keywords\": [\"(从我的回答中提取出的、与岗位要求高度相关的关键词1)\", \"(关键词2)\", \"(关键词3)\"],\n"
        "    \"missing_keywords\": [\"(根据岗位要求，我应该提及但未提及的核心关键词1)\", \"(关键词2)\", \"(关键词3)\"],\n"
        "    \"analysis_comment\": \"(一段关于我关键词使用情况的简短分析)\"\n"
        "  },\n"
        "  \"star_analysis\": [\n"
        "    {\n"
        "      \"question_sequence\": (问题序号，例如 1),\n"
        "      \"is_behavioral_question\": (判断这个问题是否是行为面试题，true/false),\n"
        "      \"conforms_to_star\": (判断我的回答是否符合STAR法则，true/false),\n"
        "      \"star_feedback\": \"(如果是不符合，请分点给出具体的改进建议，例如'Situation描述不清'或'缺少量化的Result'；如果符合，则表扬)\"\n"
        "    }\n"
        "  ]\n"
        "}"
    )

    try:
        messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]
        report_data = _call_openai_api(api_key, model, messages, 3500, 0.5)

        if 'overall_score' in report_data:
            try:
                report_data['overall_score'] = int(report_data['overall_score'])
            except:
                report_data['overall_score'] = 0
        if 'ability_scores' in report_data and isinstance(report_data.get('ability_scores'), list):
            for item in report_data['ability_scores']:
                try:
                    item['score'] = float(item.get('score', 0))
                except:
                    item['score'] = 0
        return report_data
    except Exception as e:
        print(f"调用 AI 生成最终报告时发生错误: {e}")
        return {"error": f"生成报告失败: {e}"}


def polish_description_by_ai(original_html: str, user: User, job_position: str = None) -> str:
    api_key, model = _get_user_ai_config(user)
    if not api_key or not model:
        return "<p>AI 服务未配置，无法进行润色。</p>"

    system_prompt = (
        "你是一位顶级的简历优化专家和资深 HR，尤其擅长使用 STAR 法则优化工作和项目描述。"
        "规则：必须保持并返回与用户输入完全相同的 HTML 结构（如 <ul>, <li>），只修改文本内容。"
    )
    job_context = f" 这段描述是为应聘 '{job_position}' 岗位准备的。" if job_position else ""
    user_prompt = (
        f"请根据 STAR 法则，优化以下简历描述。{job_context}\n\n"
        f"原始 HTML 内容：\n```html\n{original_html}\n```\n\n"
        f"请严格按照以下 JSON 格式返回优化后的 HTML 内容：\n"
        "{\"polished_html\": \"(这里是你优化后的 HTML 字符串)\"}"
    )

    try:
        messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]
        result_json = _call_openai_api(api_key, model, messages, 2048, 0.5)
        return result_json.get("polished_html", original_html)
    except Exception as e:
        print(f"调用 AI 进行文本润色时发生错误: {e}")
        return original_html


# ai_interview_backend/interviews/ai_services.py

# ... (其他 imports 和函数保持不变) ...

def analyze_resume_against_jd(resume_text: str, jd_text: str, user: User) -> dict:
    """
    【豪华升级版】
    根据给定的岗位描述(JD)，从多个维度深度分析简历，并返回结构化的数据报告。
    """
    api_key, model = _get_user_ai_config(user)
    if not api_key or not model:
        return {"error": "AI 服务未配置，无法进行分析。"}

    system_prompt = (
        "你是一位顶级的职业规划导师和资深技术招聘官，拥有15年以上的经验，以分析精准、洞察深刻、要求严格著称。"
        "你的任务是：像对待一份真实投递的简历一样，基于一份岗位描述（JD）和一份候选人简历，进行一次全面、深度、数据驱动的评估。"
    )

    user_prompt = (
        f"请严格遵循以下步骤，对提供的简历和JD进行分析，并以一个完整的JSON对象格式返回结果，不要包含任何额外的解释。\n\n"
        f"--- 岗位描述 (JD) ---\n"
        f"{jd_text}\n"
        f"--- JD 结束 ---\n\n"
        f"--- 候选人简历 ---\n"
        f"{resume_text}\n"
        f"--- 简历结束 ---\n\n"
        f"分析步骤与返回的JSON格式要求如下:\n"
        "{\n"
        "  \"overall_score\": (请给出一个0-100的整数，代表简历与JD的整体匹配度得分),\n"

        "  \"ability_scores\": [\n"
        "    {\"name\": \"岗位技能匹配度\", \"score\": (请根据简历中体现的技能与JD要求的吻合度，给出0-5分，可有1位小数)},\n"
        "    {\"name\": \"项目经验含金量\", \"score\": (请评估简历中的项目经验是否复杂、有深度、与JD相关，给出0-5分)},\n"
        "    {\"name\": \"经验的量化成果\", \"score\": (请评估简历中的描述是否大量使用了具体数字来量化工作成果，给出0-5分)},\n"
        "    {\"name\": \"简历专业性\", \"score\": (请评估简历的整体排版、措辞和专业度，有无错别字等，给出0-5分)}\n"
        "  ],\n"

        "  \"keyword_analysis\": {\n"
        "    \"jd_keywords\": [\"从JD中提取出5-8个最核心的技术/经验关键词\"],\n"
        "    \"matched_keywords\": [\"在简历中明确匹配到的JD关键词\"],\n"
        "    \"missing_keywords\": [\"简历中缺失的、但JD中很重要的关键词\"]\n"
        "  },\n"
        "  \"strengths_analysis\": [\n"
        "    \"(分点列出2-3条简历中最突出的、与JD高度匹配的亮点)\"\n"
        "  ],\n"
        "  \"weaknesses_analysis\": [\n"
        "    \"(分点列出2-3条简历中明显的不足或与JD不匹配之处)\"\n"
        "  ],\n"
        "  \"suggestions\": [\n"
        "    {\n"
        "      \"module\": \"(建议修改的简历模块名，如：'项目经历', '专业技能')\",\n"
        "      \"suggestion\": \"(提供一条非常具体、可执行的修改建议，例如：'在AI模拟面试平台的项目描述中，将“提升了页面加载速度”具体化为“通过代码分割和图片懒加载，将首页的LCP时间从3.2s优化至1.8s”。')\"\n"
        "    }\n"
        "  ]\n"
        "}"
    )

    try:
        messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]
        analysis_report = _call_openai_api(api_key, model, messages, 3072, 0.6)

        # --- 【核心新增】添加数据清洗逻辑，确保分数是数字 ---
        if 'overall_score' in analysis_report and not isinstance(analysis_report['overall_score'], int):
            try:
                analysis_report['overall_score'] = int(analysis_report['overall_score'])
            except (ValueError, TypeError):
                analysis_report['overall_score'] = 0

        if 'ability_scores' in analysis_report and isinstance(analysis_report.get('ability_scores'), list):
            for item in analysis_report['ability_scores']:
                if 'score' in item and not isinstance(item['score'], (int, float)):
                    try:
                        item['score'] = float(item['score'])
                    except (ValueError, TypeError):
                        item['score'] = 0

        return analysis_report

    except Exception as e:
        print(f"调用 AI 进行简历分析时发生错误: {e}")
        return {"error": f"分析失败，AI服务暂时不可用: {e}"}


def generate_resume_by_ai(name: str, position: str, experience_years: str, keywords: str, user: User) -> dict:
    api_key, model = _get_user_ai_config(user)
    if not api_key or not model:
        return {"error": "AI 服务未配置"}

    system_prompt = (
        "你是一位世界顶级的简历撰写专家，任务是根据用户的核心信息，生成一份专业、完整的简历。"
        "你必须严格按照我指定的 JSON 格式返回，包含 'sidebar' 和 'main' 两个区域的模块数组。"
    )
    user_prompt = (
        f"请为我生成一份简历。我的核心信息如下：\n"
        f"- 姓名: {name}\n"
        f"- 期望岗位: {position}\n"
        f"- 工作年限: {experience_years}\n"
        f"- 其他关键词或个人优势: {keywords}\n\n"
        f"请为我生成“基本信息”、“教育背景”、“工作经历”、“项目经历”、“专业技能”和“自我评价”这几个核心模块。"
        f"内容需要你根据期望岗位进行专业的、合理的虚构和扩展，使其看起来非常真实和有竞争力。"
        f"返回的 JSON 结构必须如下（不要包含任何额外解释）：\n"
        "{\n"
        "  \"sidebar\": [\n"
        "    {\n"
        "      \"id\": \"(生成一个uuid)\",\n"
        "      \"componentName\": \"BaseInfoModule\",\n"
        "      \"moduleType\": \"BaseInfo\",\n"
        "      \"title\": \"基本信息\",\n"
        "      \"props\": {\n"
        "        \"show\": true,\n"
        "        \"name\": \"(用户的姓名)\",\n"
        "        \"photo\": \"\",\n"
        "        \"items\": [\n"
        "          {\"id\": \"(uuid)\", \"label\": \"电话\", \"value\": \"138-xxxx-xxxx\"},\n"
        "          {\"id\": \"(uuid)\", \"label\": \"邮箱\", \"value\": \"xxxx@email.com\"}\n"
        "        ]\n"
        "      }\n"
        "    },\n"
        "    {\n"
        "      \"id\": \"(uuid)\",\n"
        "      \"componentName\": \"SkillsModule\",\n"
        "      \"moduleType\": \"Skills\",\n"
        "      \"title\": \"专业技能\",\n"
        "      \"props\": {\n"
        "        \"show\": true,\n"
        "        \"title\": \"专业技能\",\n"
        "        \"skills\": [\n"
        "          {\"id\": \"(uuid)\", \"name\": \"(根据岗位生成的核心技能1)\", \"proficiency\": \"精通\"},\n"
        "          {\"id\": \"(uuid)\", \"name\": \"(技能2)\", \"proficiency\": \"熟练\"}\n"
        "        ]\n"
        "      }\n"
        "    }\n"
        "  ],\n"
        "  \"main\": [\n"
        "    {\n"
        "      \"id\": \"(uuid)\",\n"
        "      \"componentName\": \"SummaryModule\",\n"
        "      \"moduleType\": \"Summary\",\n"
        "      \"title\": \"自我评价\",\n"
        "      \"props\": {\n"
        "        \"show\": true,\n"
        "        \"title\": \"自我评价\",\n"
        "        \"summary\": \"(生成一段2-3句话分点的、高度概括的自我评价)\"\n"
        "      }\n"
        "    },\n"
        "    {\n"
        "      \"id\": \"(uuid)\",\n"
        "      \"componentName\": \"WorkExpModule\",\n"
        "      \"moduleType\": \"WorkExp\",\n"
        "      \"title\": \"工作经历\",\n"
        "      \"props\": {\n"
        "        \"show\": true,\n"
        "        \"title\": \"工作经历\",\n"
        "        \"experiences\": [\n"
        "          {\n"
        "            \"id\": \"(uuid)\",\n"
        "            \"company\": \"(虚构一个知名的相关公司)\",\n"
        "            \"position\": \"(相关职位)\",\n"
        "            \"dateRange\": [\"(合理的开始年份)\", \"(合理的结束年份)\"],\n"
        "            \"description\": \"(使用STAR法则分点生成一段非常有吸引力的工作描述，包含量化结果)\"\n"
        "          }\n"
        "        ]\n"
        "      }\n"
        "    },\n"
        "    {\n"
        "      \"id\": \"(uuid)\",\n"
        "      \"componentName\": \"ProjectModule\",\n"
        "      \"moduleType\": \"Project\",\n"
        "      \"title\": \"项目经历\",\n"
        "      \"props\": {\n"
        "        \"show\": true,\n"
        "        \"title\": \"项目经历\",\n"
        "        \"projects\": [\n"
        "          {\n"
        "            \"id\": \"(uuid)\",\n"
        "            \"name\": \"(虚构一个亮眼的相关项目)\",\n"
        "            \"role\": \"(核心角色)\",\n"
        "            \"dateRange\": [\"(合理的开始年份)\", \"(合理的结束年份)\"],\n"
        "            \"description\": \"(使用STAR法则分点生成一段非常有吸引力的项目描述)\",\n"
        "            \"techStack\": \"(项目使用的技术栈)\"\n"
        "          }\n"
        "        ]\n"
        "      }\n"
        "    },\n"
        "    {\n"
        "      \"id\": \"(uuid)\",\n"
        "      \"componentName\": \"EducationModule\",\n"
        "      \"moduleType\": \"Education\",\n"
        "      \"title\": \"教育背景\",\n"
        "      \"props\": {\n"
        "        \"show\": true,\n"
        "        \"title\": \"教育背景\",\n"
        "        \"educations\": [\n"
        "          {\n"
        "            \"id\": \"(uuid)\",\n"
        "            \"school\": \"(虚构一所不错的大学)\",\n"
        "            \"major\": \"(相关专业)\",\n"
        "            \"degree\": \"(本科/硕士)\",\n"
        "            \"dateRange\": [\"(合理的开始年份)\", \"(合理的结束年份)\"],\n"
        "            \"description\": \"\"\n"
        "          }\n"
        "        ]\n"
        "      }\n"
        "    }\n"
        "  ]\n"
        "}"
    )
    try:
        messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]
        resume_json = _call_openai_api(api_key, model, messages, 4096, 0.8)
        return resume_json
    except Exception as e:
        print(f"调用 AI 生成简历时发生错误: {e}")
        return {"error": f"AI 生成失败: {e}"}