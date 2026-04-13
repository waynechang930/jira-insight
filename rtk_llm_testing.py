
import openai
from openai import OpenAI
 

GOOGLE_IMPROVEMENT_PROMPT = """
# Role Definition
You are a Senior Technical Product Manager and Android System Expert.
Your task is to review the following list of recent Jira issues from our database and identify items that "require Google's assistance to resolve, fix (bugs), or improve."

# Context
These issues may cover Google-related technologies such as Android OS, Framework, Google TV, GMS (Google Mobile Services), Chromecast, Widevine, etc.
Please strictly exclude pure internal App logic errors or third-party hardware issues unrelated to Google.
Look for characteristics like:
1. Involves Android OS, Framework, Google TV, GMS, Chromecast, Widevine, etc.
2. Shows low-level crashes, memory leaks, or Hardware Abstraction Layer (HAL) anomalies.
3. Engineers mention phrases implying "out of our hands," "waiting for upstream fix," or "system limitation" in the resolution/description.

# Input Data
<issues>
{issue_list}
</issues>

# Instructions
1. Filter & Categorize: Select issues from the list above that are clearly related to the Google system level or require a patch/API support from Google.
2. Priority Sorting: Categorize them into High, Medium, and Low priority based on severity (e.g., system crash, core UX impact, security issue).
3. Summarize & Output: Group similar types of issues together and output in Markdown format. **You MUST strictly sort them from Highest to Lowest priority.**

# Output Format
Please use the following Markdown format (Write the report entirely in English):

## 🔴 High Priority - Severely impacts UX or system stability
* **[Summarized Core Issue Name]**
  * **Related Jira IDs**: [List the Jira Keys]
  * **Issue Description & Impact**: [Brief description]
  * **Specific Request for Google**: [e.g., Need a bug fix in Android Framework, or expose a specific API]

## 🟡 Medium Priority - Functional anomaly but has a workaround or non-core feature
(Same format as above)

## 🟢 Low Priority - UI/UX tweaks or future feature requests
(Same format as above)

# Constraints
1. **CRITICAL: DO NOT repeat the same issue multiple times.** Every issue must be listed exactly ONCE.
2. Group identical or highly similar issues together under a single bullet point by combining their Jira IDs.
3. If you have no more unique issues to list, stop generating immediately.

---
If there are absolutely no issues requiring Google's assistance in the provided data, simply reply exactly with: "No system-level issues requiring Google's assistance were found in this batch."
""" 
# 配置 API 客戶端
client = OpenAI(
    base_url="https://devops.realtek.com/realgpt-api/openai-compatible/v1",  # 替換為你的 LLM API 端點
    api_key="2425893518e83a13b1e1ac88fb5157bc"  # 替換為你的 API 金鑰
)
 
def chat_with_llm(prompt, model="fast", max_tokens=100):
    issue_list_text = ""
    try:
        # 發送聊天完成請求
        response = client.chat.completions.create(
                model=model, 
                messages=[
                    {"role": "system", "content": "You are a sharp Android OS system expert. DO NOT repeat the same content."},
                    {"role": "user", "content": GOOGLE_IMPROVEMENT_PROMPT.format(issue_list=issue_list_text)}
                ],
                temperature=0.4,       # Slightly increased to break loops
                frequency_penalty=1.2, # Penalize repeating exactly the same words
                presence_penalty=0.6,  # Encourage moving to new topics
                stream=False
            )
        # 提取並返回回應
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"Error: {str(e)}"
 
# 使用範例
if __name__ == "__main__":
    user_prompt = "Hello, can you tell me a joke?"
    response = chat_with_llm(user_prompt)
    print("LLM Response:", response)
