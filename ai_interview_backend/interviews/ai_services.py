import os
import json
from openai import OpenAI
from dotenv import load_dotenv
from users.models import User
from system.models import AISetting

load_dotenv()
SYSTEM_DEFAULT_API_KEY = os.getenv("DEEPSEEK_API_KEY")


def _get_user_ai_config(user: User) -> (str, str):
    """
    一个内部辅助函数，用于获取用户的API Key和模型名称。
    如果用户未设置，则回退到系统默认值。
    """
    api_key = None
    model_name = "deepseek-chat"  # 默认模型

    try:
        user_setting = user.ai_setting
        if user_setting and user_setting.api_key:
            api_key = user_setting.api_key
            model_name = user_setting.ai_model
            print(f"正在为用户 {user.username} 使用自定义 AI 配置。")
    except AISetting.DoesNotExist:
        print(f"用户 {user.username} 没有自定义设置，将使用系统默认 Key。")
        pass

    # 如果用户没有自定义 Key，则使用系统默认 Key
    if not api_key:
        api_key = SYSTEM_DEFAULT_API_KEY
        print("回退到使用系统默认 API Key。")

    return api_key, model_name


def generate_first_question(job_position: str, user: User, resume_text: str = None) -> str:
    api_key, model_name = _get_user_ai_config(user)
    if not api_key:
        return "系统AI服务未配置，无法生成问题。"

    system_prompt = (
        "你是一位顶尖公司的资深技术面试官，以提问精准、深入、专业著称。"
        "你的任务是开启一场关于特定岗位的面试。"
    )
    if resume_text:
        user_prompt = (
            f"我正在应聘 '{job_position}' 岗位。这是我的简历内容：\n\n"
            f"--- 简历开始 ---\n{resume_text}\n--- 简历结束 ---\n\n"
            "请仔细阅读我的简历，并提出一个有针对性的、能让我展开介绍简历亮点的开场问题。"
            "例如，你可以问 '我在你的简历中看到你做过XX项目，能详细介绍一下吗？'。"
            "请直接返回问题本身，不要包含任何如“你好”之类的问候语或多余的解释。"
        )
    else:
        user_prompt = (
            f"我正在应聘 '{job_position}' 岗位，但未提供简历。"
            "请为我生成一个通用但热情的开场问题，要求我进行一个简洁的自我介绍。"
            "请直接返回问题本身，不要包含多余内容。"
        )

    try:
        client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            stream=False,
            max_tokens=300,
            temperature=0.7,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"调用 DeepSeek API 时发生错误: {e}")
        return f"你好，欢迎参加 {job_position} 的面试。很抱歉，我的AI大脑暂时出了一点小问题。不过没关系，我们可以从一个经典问题开始：请先做一个简单的自我介绍吧。"


def analyze_and_generate_next(job_position: str, interview_history: list, user: User) -> dict:
    api_key, model_name = _get_user_ai_config(user)
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
        client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            stream=False,
            max_tokens=500,
            temperature=0.8,
            response_format={"type": "json_object"},
        )
        ai_response = json.loads(response.choices[0].message.content)
        return ai_response
    except Exception as e:
        print(f"调用 AI 进行分析和提问时发生错误: {e}")
        return {"feedback": "AI 在分析时遇到了一点小问题。",
                "next_question": "让我们换个问题继续：请谈谈你遇到的最大的技术挑战是什么？"}


def generate_final_report(job_position: str, interview_history: list, user: User) -> dict:
    """
    根据完整的面试历史，生成一份包含多维度能力评分的综合报告。
    """
    # ... (获取 api_key 和 model_name 的逻辑保持不变) ...
    api_key, model_name = _get_user_ai_config(user)
    if not api_key:
        return {"error": "AI服务未配置。"}

    history_prompt_part = ""
    for i, turn in enumerate(interview_history):
        history_prompt_part += f"问题 {i + 1}: {turn['question']}\n"
        history_prompt_part += f"候选人回答 {i + 1}: {turn['answer']}\n\n"

    system_prompt = (
        "你是一位顶级的职业规划师和面试分析专家。"
        "你的任务是基于一场完整的面试记录，为候选人生成一份专业、数据驱动、富有洞察力的面试报告。"
    )
    user_prompt = (
        f"我刚刚完成了一场关于 '{job_position}' 岗位的模拟面试。完整的问答记录如下：\n\n"
        f"--- 面试记录开始 ---\n{history_prompt_part}--- 面试记录结束 ---\n\n"
        "请你对我本次面试的整体表现进行综合评估，并严格按照下面的 JSON 格式返回你的分析报告。"
        "所有评分都为0-5分，可以有小数。所有文本内容需客观、专业且有建设性。\n"
        "{\n"
        "  \"overall_score\": \"(一个0到100的整数，代表综合得分)\",\n"
        "  \"overall_comment\": \"(一段100字左右的总体评价)\",\n"
        "  \"ability_scores\": [\n"
        "    {\"name\": \"专业知识\", \"score\": (0-5分)},\n"
        "    {\"name\": \"项目经验\", \"score\": (0-5分)},\n"
        "    {\"name\": \"逻辑思维\", \"score\": (0-5分)},\n"
        "    {\"name\": \"沟通表达\", \"score\": (0-5分)},\n"
        "    {\"name\": \"求职动机\", \"score\": (0-5分)}\n"
        "  ],\n"
        "  \"strength_analysis\": \"(关于本次面试亮点的分析)\",\n"
        "  \"weakness_analysis\": \"(关于本次面试不足之处的分析)\",\n"
        "  \"improvement_suggestions\": [\n"
        "    \"(第一条具体的改进建议)\",\n"
        "    \"(第二条具体的改进建议)\"\n"
        "  ]\n"
        "}"
    )

    try:
        client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            stream=False,
            max_tokens=2500,
            temperature=0.6,
            response_format={"type": "json_object"},
        )
        import json
        report_data = json.loads(response.choices[0].message.content)
        # 安全地转换分数为数字
        if 'overall_score' in report_data and isinstance(report_data.get('overall_score'), str):
            try:
                report_data['overall_score'] = int(report_data['overall_score'])
            except:
                report_data['overall_score'] = 0
        if 'ability_scores' in report_data and isinstance(report_data.get('ability_scores'), list):
            for item in report_data['ability_scores']:
                if 'score' in item and isinstance(item.get('score'), (str, int)):
                    try:
                        item['score'] = float(item['score'])
                    except:
                        item['score'] = 0
        return report_data
    except Exception as e:
        print(f"调用 AI 生成最终报告时发生错误: {e}")
        return {"error": f"生成报告失败: {e}"}