import os
import json
from openai import OpenAI
from dotenv import load_dotenv
from users.models import User
from system.models import AISetting

load_dotenv()
SYSTEM_DEFAULT_API_KEY = os.getenv("DEEPSEEK_API_KEY")
# 【核心修正】定义系统级默认模型，以防用户没有任何设置
DEFAULT_MODEL_SLUG = "deepseek-chat"
DEFAULT_BASE_URL = "https://api.deepseek.com"


def _get_user_ai_config(user: User) -> (str, str, str):
    """
    获取用户的API Key, 模型调用名(slug), 和 Base URL。
    如果用户未设置，则回退到系统默认值。
    """
    api_key = None
    model_slug = DEFAULT_MODEL_SLUG
    base_url = DEFAULT_BASE_URL

    try:
        user_setting = user.ai_setting
        if user_setting.api_key:
            api_key = user_setting.api_key
            print(f"正在为用户 {user.username} 使用自定义 API Key。")

        if user_setting.ai_model:
            model_slug = user_setting.ai_model.model_slug
            base_url = user_setting.ai_model.base_url
            print(f"用户 {user.username} 使用自定义模型: {model_slug} @ {base_url}")

    except AISetting.DoesNotExist:
        print(f"用户 {user.username} 没有自定义设置，将使用系统默认配置。")
        pass

    if not api_key:
        api_key = SYSTEM_DEFAULT_API_KEY
        print("回退到使用系统默认 API Key。")

    return api_key, model_slug, base_url


def _call_openai_api(api_key, model_slug, base_url, messages, max_tokens, temperature):
    """一个统一调用 OpenAI API 的辅助函数"""
    # 【核心修正】确保 base_url 没有多余的 /v1
    # DeepSeek 的 Chat API 不需要 /v1
    if "deepseek.com" in base_url and "/v1" in base_url:
        base_url = base_url.replace("/v1", "")

    client = OpenAI(api_key=api_key, base_url=base_url)
    response = client.chat.completions.create(
        model=model_slug,
        messages=messages,
        stream=False,
        max_tokens=max_tokens,
        temperature=temperature,
        response_format={"type": "json_object"},
    )
    return json.loads(response.choices[0].message.content)


# 【新增】专门处理流式调用的函数
def _call_openai_api_stream(api_key, model_slug, base_url, messages, max_tokens, temperature):
    if "deepseek.com" in base_url and "/v1" in base_url:
        base_url = base_url.replace("/v1", "")
    client = OpenAI(api_key=api_key, base_url=base_url)
    stream = client.chat.completions.create(
        model=model_slug, messages=messages, stream=True,
        max_tokens=max_tokens, temperature=temperature
    )
    for chunk in stream:
        content = chunk.choices[0].delta.content or ""
        yield content
def generate_first_question(job_position: str, user: User, resume_text: str = None) -> str:
    # 【核心修正】用三个变量接收
    api_key, model_slug, base_url = _get_user_ai_config(user)
    if not api_key:
        return "系统AI服务未配置，无法生成问题。"

    system_prompt = (
        "你是一位顶尖公司的资深技术面试官，以提问精准、深入、专业著称。"
        "你的任务是开启一场关于特定岗位的面试。"
    )
    # 【终极核心修正】为所有 user_prompt 添加 JSON 指令
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
        ai_response = _call_openai_api(api_key, model_slug, base_url, messages, 300, 0.7)
        return ai_response.get("question", "你好，请做个自我介绍吧。")
    except Exception as e:
        print(f"调用 AI 生成第一问时发生错误: {e}")
        return f"你好，欢迎参加 {job_position} 的面试。很抱歉，我的AI大脑暂时出了一点小问题。不过没关系，我们可以从一个经典问题开始：请先做一个简单的自我介绍吧。"


def analyze_and_generate_next(job_position: str, interview_history: list, user: User) -> dict:
    # 【核心修正】用三个变量接收
    api_key, model_slug, base_url = _get_user_ai_config(user)
    if not api_key:
        return {"feedback": "AI服务未配置。", "next_question": "面试无法继续。"}

    history_prompt_part = ""
    for i, turn in enumerate(interview_history):
        history_prompt_part += f"第 {i + 1} 轮:\n"
        history_prompt_part += f"面试官 (你): {turn['question']}\n"
        history_prompt_part += f"候选人 (我): {turn['answer']}\n\n"

    latest_answer = interview_history[-1]['answer']
    system_prompt = (
        "你是一位顶尖公司的资深技术面试官，以提问精准、分析深刻著称。"
        "你的任务是：1. 对候选人的最新回答进行简短、专业、有建设性的评价。2. 基于整个对话历史，提出下一个有深度的追问。"
    )
    user_prompt = (
        f"以下是关于 '{job_position}' 岗位的面试对话历史：\n\n"
        f"{history_prompt_part}"
        f"请严格按照以下 JSON 格式返回你的回应，不要包含任何额外的解释：\n"
        "{\n"
        f"  \"feedback\": \"(这里是你对候选人最新回答 '{latest_answer}' 的简评，大约30-50字)\",\n"
        f"  \"next_question\": \"(这里是你的下一个问题)\"\n"
        "}"
    )

    try:
        messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]
        return _call_openai_api(api_key, model_slug, base_url, messages, 500, 0.8)
    except Exception as e:
        print(f"调用 AI 进行分析和提问时发生错误: {e}")
        return {"feedback": "AI 在分析时遇到了一点小问题。",
                "next_question": "让我们换个问题继续：请谈谈你遇到的最大的技术挑战是什么？"}
# 【改造】所有 AI 调用函数，现在返回一个生成器
#
# 【新增】非流式函数，专门用于分析回答并生成简评
def analyze_answer(job_position: str, question: str, answer: str, user: User) -> str:
    api_key, model_slug, base_url = _get_user_ai_config(user)
    if not api_key: return "AI服务未配置，无法生成简评。"

    system_prompt = "你是一位专业的面试官，任务是根据候选人的回答给出一个简短、有建设性的评价。"
    user_prompt = (
        f"我正在面试 '{job_position}' 岗位。\n"
        f"面试官提问: {question}\n"
        f"我的回答: {answer}\n\n"
        "请对我的回答给出一个大约30-50字的简评。直接返回评价本身，不要包含多余内容。"
    )
    try:
        client = OpenAI(api_key=api_key, base_url=base_url)
        response = client.chat.completions.create(
            model=model_slug, messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            stream=False, max_tokens=200, temperature=0.6
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"调用 AI 生成简评时发生错误: {e}")
        return "AI 在分析时遇到了一点小问题。"


# 【改造】流式函数，只负责生成第一个问题
def generate_first_question_stream(job_position: str, user: User, resume_text: str = None):
    api_key, model_slug, base_url = _get_user_ai_config(user)
    if not api_key:
        yield "系统AI服务未配置，无法生成问题。"
        return

    system_prompt = "你是一位专业的AI面试官。请直接返回问题本身，不要包含任何多余的解释或标题。"
    if resume_text:
        user_prompt = f"我正在应聘 '{job_position}' 岗位。请根据我的简历：'{resume_text[:1000]}...'，提出一个有针对性的开场问题。"
    else:
        user_prompt = f"我正在应聘 '{job_position}' 岗位，请为我生成一个通用但热情的开场问题，要求我进行一个简洁的自我介绍。"

    try:
        messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]
        yield from _call_openai_api_stream(api_key, model_slug, base_url, messages, 300, 0.7)
    except Exception as e:
        print(f"调用 AI 生成第一问时发生错误: {e}")
        yield f"你好，欢迎参加 {job_position} 的面试。很抱歉，我的AI大脑暂时出了一点小问题。不过没关系，我们可以从一个经典问题开始：请先做一个简单的自我介绍吧。"


# 【改造】流式函数，只负责生成下一个问题
def generate_next_question_stream(job_position: str, interview_history: list, user: User):
    api_key, model_slug, base_url = _get_user_ai_config(user)
    if not api_key:
        yield "AI服务未配置。"
        return

    history_prompt_part = ""
    for turn in interview_history:
        history_prompt_part += f"面试官: {turn['question']}\n我: {turn['answer']}\n\n"
    system_prompt = "你是一位专业的AI面试官，任务是根据对话历史提出下一个有深度的追问。直接返回问题本身。"
    user_prompt = f"这是关于 '{job_position}' 的面试历史:\n{history_prompt_part}\n现在，请提出你的下一个问题。"

    try:
        messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]
        yield from _call_openai_api_stream(api_key, model_slug, base_url, messages, 500, 0.8)
    except Exception as e:
        print(f"调用 AI 生成下一问时发生错误: {e}")
        yield "请谈谈你遇到的最大的技术挑战是什么？"


def generate_final_report(job_position: str, interview_history: list, user: User) -> dict:
    """
    【终极版】
    根据完整的面试历史，生成一份包含多维度能力评分、关键词分析和STAR法则分析的综合报告。
    """
    # 【核心修正】用三个变量接收
    api_key, model_slug, base_url = _get_user_ai_config(user)
    if not api_key:
        return {"error": "AI服务未配置，无法生成报告。"}

    history_prompt_part = ""
    for i, turn in enumerate(interview_history):
        history_prompt_part += f"--- 问题 {i + 1} ---\n"
        history_prompt_part += f"面试官提问: {turn['question']}\n"
        history_prompt_part += f"我的回答: {turn['answer']}\n\n"

    system_prompt = (
        "你是一位顶级的职业规划师和面试分析专家，尤其擅长结构化思维分析和关键词提取。"
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
        "      \"star_feedback\": \"(如果是不符合，请给出具体的改进建议，例如'Situation描述不清'或'缺少量化的Result'；如果符合，则表扬)\"\n"
        "    }\n"
        "  ]\n"
        "}"
    )

    try:
        messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]
        report_data = _call_openai_api(api_key, model_slug, base_url, messages, 3500, 0.5)

        # --- 安全地转换分数为数字 (保持不变) ---
        if 'overall_score' in report_data and isinstance(report_data.get('overall_score'), str):
            try:
                report_data['overall_score'] = int(report_data['overall_score'])
            except:
                report_data['overall_score'] = 0
        if 'ability_scores' in report_data and isinstance(report_data.get('ability_scores'), list):
            for item in report_data['ability_scores']:
                if 'score' in item and isinstance(item.get('score'), (str, int, float)):
                    try:
                        item['score'] = float(item['score'])
                    except:
                        item['score'] = 0

        return report_data

    except Exception as e:
        print(f"调用 AI 生成最终报告时发生错误: {e}")
        return {"error": f"生成报告失败: {e}"}


def polish_description_by_ai(original_html: str, user: User, job_position: str = None) -> str:
    """
    使用 AI 优化一段工作/项目描述的 HTML 内容。
    :param original_html: 用户在富文本编辑器中输入的原始 HTML。
    :param user: 当前用户，用于获取 AI 配置。
    :param job_position: (可选) 目标岗位，让优化更有针对性。
    :return: 优化后的 HTML 字符串。
    """
    api_key, model_slug, base_url = _get_user_ai_config(user)
    if not api_key:
        return "<p>AI 服务未配置，无法进行润色。</p>"

    # 构造系统 Prompt
    system_prompt = (
        "你是一位顶级的简历优化专家和资深 HR，尤其擅长使用 STAR 法则（Situation, Task, Action, Result）来优化工作和项目描述。"
        "你的任务是：润色用户提供的描述，使其更具吸引力、突出量化成果，并保持专业的书面语风格。"
        "重要规则：你必须保持并返回与用户输入完全相同的 HTML 结构（例如 <ul>, <li>, <strong> 等），只修改文本内容。"
    )

    # 构造用户 Prompt
    job_context = f" 这段描述是为应聘 '{job_position}' 岗位准备的。" if job_position else ""
    user_prompt = (
        f"请根据 STAR 法则，优化以下这段简历描述。{job_context}\n\n"
        f"原始 HTML 内容如下：\n"
        f"```html\n{original_html}\n```\n\n"
        f"请严格按照以下 JSON 格式返回你优化后的 HTML 内容，不要包含任何额外的解释或代码块标记：\n"
        "{\n"
        "  \"polished_html\": \"(这里是你优化后的、保持了原有结构的 HTML 字符串)\"\n"
        "}"
    )

    try:
        messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]
        # 注意：这里我们强制要求返回 JSON 对象
        client = OpenAI(api_key=api_key, base_url=base_url)
        response = client.chat.completions.create(
            model=model_slug,
            messages=messages,
            stream=False,
            max_tokens=2048,  # 给予足够的空间来生成内容
            temperature=0.5,  # 温度稍低，确保专业性
            response_format={"type": "json_object"},
        )

        result_json = json.loads(response.choices[0].message.content)
        return result_json.get("polished_html", original_html)  # 如果 AI 返回格式错误，则返回原文

    except Exception as e:
        print(f"调用 AI 进行文本润色时发生错误: {e}")
        # 在出错时，最好返回原文，避免用户内容丢失
        return original_html


def analyze_resume_against_jd(resume_text: str, jd_text: str, user: User) -> dict:
    """
    根据给定的岗位描述(JD)，深度分析简历内容，并返回结构化的优化报告。

    :param resume_text: 简历的纯文本内容。
    :param jd_text: 目标岗位的 JD 纯文本内容。
    :param user: 当前用户，用于获取 AI 配置。
    :return: 一个包含分析结果的字典。
    """
    api_key, model_slug, base_url = _get_user_ai_config(user)
    if not api_key:
        return {"error": "AI 服务未配置，无法进行分析。"}

    system_prompt = (
        "你是一位顶级的职业规划导师和资深招聘专家，拥有极其敏锐的洞察力，擅长将简历与岗位要求进行精确匹配和分析。"
        "你的任务是：基于一份岗位描述（JD）和一份候选人简历，进行一次全面、深度、富有建设性的评估。"
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
        "  \"keyword_analysis\": {\n"
        "    \"jd_keywords\": [\"从JD中提取出5-8个最核心的技能/经验关键词\"],\n"
        "    \"matched_keywords\": [\"在简历中明确匹配到的JD关键词\"],\n"
        "    \"missing_keywords\": [\"简历中缺失的、但JD中很重要的关键词\"]\n"
        "  },\n"
        "  \"strengths_analysis\": [\n"
        "    \"(列出2-3条简历中最突出的、与JD高度匹配的亮点，例如：'项目经历中的XX技术栈与JD要求完全吻合')\"\n"
        "  ],\n"
        "  \"weaknesses_analysis\": [\n"
        "    \"(列出2-3条简历中明显的不足或与JD不匹配之处，例如：'缺乏JD中要求的XX项目管理经验')\"\n"
        "  ],\n"
        "  \"suggestions\": [\n"
        "    {\n"
        "      \"module\": \"(建议修改的简历模块名，如：'项目经历', '专业技能', '自我评价')\",\n"
        "      \"suggestion\": \"(提供一条非常具体、可执行的修改建议，例如：'在AI模拟面试平台的项目描述中，增加关于并发处理或性能优化的具体数据，以呼应JD中的高并发要求。')\"\n"
        "    }\n"
        "  ]\n"
        "}"
    )

    try:
        messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]

        client = OpenAI(api_key=api_key, base_url=base_url)
        response = client.chat.completions.create(
            model=model_slug,
            messages=messages,
            stream=False,
            max_tokens=3072,  # 给予足够的空间来生成详细报告
            temperature=0.6,
            response_format={"type": "json_object"},
        )

        analysis_report = json.loads(response.choices[0].message.content)
        # (可选) 在这里可以对AI返回的JSON进行一次校验和清洗
        return analysis_report

    except Exception as e:
        print(f"调用 AI 进行简历分析时发生错误: {e}")
        return {"error": f"分析失败，AI服务暂时不可用: {e}"}