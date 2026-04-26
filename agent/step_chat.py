import logging

from .tools.tools_def import engine, llm, query_database

from .tools.copilot.sql_code import get_db_info_prompt

from .tools.get_function_info import get_function_info

from .tools.copilot.utils.call_llm_test import call_llm


def get_step_chat_prompt(question):
    # rag_ans = rag_from_policy_func(question,llm,engine)
    rag_ans = ""
    # print(rag_ans)

    knowledge = "\nBase knowledge: \n" + rag_ans + "\n"
    database = ""

    function_set, function_info, function_import = get_function_info(question, llm, use_all_functions=True)
    if function_info == "solved":
        return "solved", rag_ans, []
    # print(function_info)

    data_prompt = get_db_info_prompt(engine, example=True, simple=True)
    database = "\nThe database content: \n" + data_prompt + "\n"

    # 彻底重构的提示词：强调基于执行结果的自主判断与纠错
    pre_prompt = """ 
You are an autonomous task executor. The input starting with "question:" contains: user intent, conversation history, an existing Markdown Checklist (if any), and the latest Execution Results (function outputs, returned data, or error messages).

Your ONLY job is to analyze the Execution Results, determine the current state, and output an updated Markdown Checklist. Do NOT output any conversational text, apologies, or explanations.

Autonomous State Judgment & Update Rules:
1. ANALYZE RESULT FIRST: Look at the latest Execution Result in the context. Ignore conversational filler and focus on the actual data returned or error traces.
2. SUCCESS: If the result contains the expected data/confirmation without errors, mark the corresponding checklist step as `- [x]`.
3. ERROR / EXCEPTION (Autonomous Correction): If the result contains error messages (e.g., KeyError, ValueError, SQL syntax error, missing parameters), DO NOT ask the user what to do. You MUST autonomously modify the failed step in the checklist to fix the error (e.g., correct the table name, change the parameter type, add missing filters) and keep it as `- [ ]`.
4. PARTIAL SUCCESS: If only part of the task was completed, mark the completed part `- [x]` and append new `- [ ]` steps for the remaining work.
5. NO RESULT YET: If it's a fresh question with no execution history, generate a fresh checklist.
6. FORMATTING: Do not mention code details. Explicitly specify database tables if used. If similar functions exist and context is insufficient to decide, add a `- [ ]` step to ask the user to choose.

Remind:
1. You Job is to plan based on the database and functions info given, not general plans.
2. You should name the database and functions needed on the step.

You can use the following functions to solve the problem:
"""
    function_prompt = """ 
Here is the functions you can import and use:
"""

    example_ans = """
[Example 1: Autonomous Error Fixing]
question:
User: Draw a graph of user ages.
Assistant:
- [ ] Retrieve Age Data from `users` table.
- [ ] Draw the Graph.
System/Execution Result: Error executing function: relation "users" does not exist. SQL query failed.
Response:
- [ ] Retrieve Age Data from `user_profiles` table.
- [ ] Draw the Graph.

[Example 2: Success State Update]
question:
User: Get user data.
Assistant:
- [ ] Query user info.
System/Execution Result: Function executed successfully. Returned 50 rows of data.
Response:
- [x] Query user info.

[Example 3: Self-Correction based on Data mismatch]
question:
User: Calculate average age.
Assistant:
- [ ] Get age data.
- [ ] Calculate average.
System/Execution Result: Function executed successfully. Returned data: [{"name": "Alice", "age": "twenty"}, {"name": "Bob", "age": "30"}]
Response:
- [x] Get age data.
- [ ] Clean and convert age strings to integers (e.g., "twenty" -> 20).
- [ ] Calculate average.
"""

    cot_prompt = "question:" + question + knowledge + database + pre_prompt + \
                 function_prompt + str(function_info) + \
                 example_ans
    return cot_prompt, rag_ans, function_import


def get_step_chat(question: str):
    cot_prompt, rag_ans, function_import = get_step_chat_prompt(question)
    # print(cot_prompt)
    ans = call_llm(cot_prompt, llm)
    return ans.content
