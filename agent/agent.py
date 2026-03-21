import logging

import pandas as pd

from .tools.base_knowledge.get_base_knowledge import get_base_knowledge
from .tools.copilot.utils.code_insert import insert_lines_into_function
from .tools.tools_def import engine, llm, query_database, exe_sql

from .tools.copilot.python_code import get_py_code
from .tools.copilot.utils.code_executor import execute_py_code
from .tools.copilot.sql_code import get_db_info_prompt

from .tools.get_function_info import get_function_info

from .utils.final_output_parse import df_to_markdown, wrap_html_url_with_html_a, \
    wrap_csv_url_with_html_a, is_local_png_path
from .utils.final_output_parse import wrap_png_url_with_markdown_image, is_png_url, is_iframe_tag
from .utils.get_config import config_data
from .utils.pd_to_csv import pd_to_csv
from .utils.pd_to_walker import pd_to_walker

STATIC_URL = config_data['static_path']

IMPORTANT_MODULE = ["import math"]
THIRD_MODULE = ["import pandas as pd", "import numpy as np",
                "import PIL", "import matplotlib",
                "import matplotlib.pyplot as plt", "import seaborn as sns"]


def get_cot_code_prompt(question, tables=None, use_all_functions=False):
    rag_ans = ""
    knowledge = ""
    rag_ans = get_base_knowledge()
    knowledge = "\nBase knowledge: \n" + rag_ans + "\n"
    # print(rag_ans)

    function_set, function_info, function_import = get_function_info(question, llm, use_all_functions)
    # print(function_info)
    if function_info == "solved":
        return "solved", rag_ans, []
    # print(function_info)

    database = ""
    if query_database in function_set or exe_sql in function_set:
        data_prompt = get_db_info_prompt(engine, tables=tables, simple=False, example=False)
        database = "\nThe database content: \n" + data_prompt + "\n"

    pre_prompt = """ 
Please use the following functions to solve the problem.
"""
    function_prompt = """ 
Here is the functions you can import and use:
"""
    module_prompt = "You can only use the third party function in " + str(THIRD_MODULE) + " !!!"

    example_code = """
    Here is an example: 
    ```python
    def func():
        import math
        import pandas as pd
        import numpy as np
        import PIL
        import matplotlib
        import matplotlib.pyplot as plt
        import seaborn as sns
        # generate code to perform operations from here
        
        yield "A01 class's grades are as follows:"  # yield some information and explanation
        yield "use table: stu_info, stu_grade"  # yield tables names before query database function
        df = exe_sql(\"\"\"
            SELECT s.student_id, s.name, g.course, g.score 
            FROM stu_info s
            JOIN stu_grade g ON s.student_id = g.student_id
            WHERE s.class = 'A01'
        \"\"\")   
        yield df  # the result of each step and function call
        
        # Branch 1: Handle None or empty DataFrame
        if df is None or df.empty:
            yield "No grade records found for A01 class in the database."
        else:
            # Branch 2: Handle single record
            if len(df) == 1:
                record = df.iloc[0]
                yield f"Only one grade record found: Student {record['name']} ({record['student_id']}) - {record['course']}: {record['score']}"
            else:
                # Branch 3: Analyze data and determine visualization strategy
                unique_courses = df['course'].nunique()
                unique_students = df['student_id'].nunique()
                
                # If analyzing by course (x-axis = course)
                if unique_courses > 1:
                    course_stats = df.groupby('course')['score'].mean().reset_index().sort_values('score', ascending=False)
                    original_count = len(course_stats)
                    
                    yield f"Found {unique_students} students with grades across {original_count} courses."
                    
                    # Determine display strategy based on number of courses
                    if original_count <= 8:
                        # Small number of courses: standard display
                        plt.figure(figsize=(10, 6))
                        plt.bar(course_stats['course'], course_stats['score'], color='steelblue', edgecolor='black', alpha=0.7)
                        plt.xticks(rotation=30, ha='right')
                    elif original_count <= 15:
                        # Medium number: larger figure + rotation
                        plt.figure(figsize=(12, 6))
                        plt.bar(course_stats['course'], course_stats['score'], color='steelblue', edgecolor='black', alpha=0.7)
                        plt.xticks(rotation=45, ha='right')
                        yield f"Displaying all {original_count} courses."
                    else:
                        # Too many courses: sampling + user notification
                        display_df = course_stats.head(12)
                        yield f"Note: There are {original_count} courses in total, which is too many to display clearly. Showing the top 12 courses by average score. Please modify your question if you want to see specific courses, e.g., 'show only Math and English' or 'show only the top 5 courses'."
                        plt.figure(figsize=(14, 6))
                        plt.bar(display_df['course'], display_df['score'], color='steelblue', edgecolor='black', alpha=0.7)
                        plt.xticks(rotation=45, ha='right')
                    
                    plt.xlabel('Course')
                    plt.ylabel('Average Score')
                    plt.title('A01 Class Average Score by Course')
                    plt.grid(axis='y', alpha=0.3)
                    plt.tight_layout()
                    path = get_save_image_path()
                    plt.savefig(path, dpi=150, bbox_inches='tight')
                    plt.close()
                    yield path
                else:
                    # Single course: show student distribution
                    yield f"Analyzing score distribution for {df['course'].iloc[0]} across {unique_students} students."
                    plt.figure(figsize=(10, 6))
                    plt.hist(df['score'], bins=8, edgecolor='black', alpha=0.7, color='steelblue')
                    plt.xlabel('Score')
                    plt.ylabel('Number of Students')
                    plt.title(f'A01 Class Score Distribution - {df["course"].iloc[0]}')
                    plt.grid(axis='y', alpha=0.3)
                    path = get_save_image_path()
                    plt.savefig(path, dpi=150, bbox_inches='tight')
                    plt.close()
                    yield path
    ```
    """

    remind_prompt = """
    Remind: 
    
    - IMPORTANT: Please use yield instead of return and print(), never use input() or any funcs that hung up the process to wait user action!
    - Please yield explanation string of each step as kind of report! Please yield some information string during the function!
    - Please yield the result of each step and function call! Please yield report many times during the function!!! not only yield at last! 
    - Please yield the tables used before query database function!!!
    - If the user just ask to introduce or explain something, just yield the answer text in code without function call.
    - None or empty DataFrame return handling for each function call is extremely important!
    
    You may draw some graphs with the given third party module.
    
    - IMPORTANT: Please save the image instead of show it, never use any funcs that hung up the process to wait user action!
    - you can save it only with generated file path: `path = get_save_image_path()`!!!
    - use different path to save different image, `get_save_image_path()` return a unique path each time you call it.
    - yield the path with single line :`yield path` , never yield the path with other str or tuple.
    - IMPORTANT: If there are too many x-axis/y-axis labels that would overlap and become unreadable, you MUST take measures:
        1. Use sampling: only display the first N items or the most important N items (e.g., top 10, top 20)
        2. Rotate labels by 45 degrees or 90 degrees using `plt.xticks(rotation=45)` or `plt.xticks(rotation=90)`
        3. Adjust figure size to be larger: `plt.figure(figsize=(width, height))`
        4. Use horizontal bar chart instead of vertical bar chart when category names are long
    - After applying these measures, yield a message to remind the user: "Due to too many categories, only the first/top N items are displayed. Please modify your question if you want to see specific items, e.g., 'show only the top 5' or 'show only categories A, B, C'."
    
    """

    cot_prompt = "question:" + question + knowledge + database + pre_prompt + \
                 function_prompt + str(function_info) + \
                 module_prompt + example_code + remind_prompt
    return cot_prompt, rag_ans, function_import


def cot_agent(question, tables=None, use_all_functions=False, retries=2, print_rows=5):
    exp = None
    for i in range(retries):
        cot_prompt, rag_ans, function_import = get_cot_code_prompt(question, tables, use_all_functions)
        print(rag_ans)
        # print(cot_prompt)
        if cot_prompt == "solved":
            return rag_ans, ""
        else:
            err_msg = ""
            for j in range(retries):
                code = get_py_code(cot_prompt + err_msg, llm)
                # print(code)
                # code = insert_yield_statements(code)
                code = insert_lines_into_function(code, function_import)
                code = insert_lines_into_function(code, IMPORTANT_MODULE)
                code = insert_lines_into_function(code, THIRD_MODULE)
                print(code)
                if code is None:
                    continue
                try:
                    result = execute_py_code(code)
                    cot_ans = ""
                    for item in result:
                        # print(item)
                        if isinstance(item, pd.DataFrame):
                            if item.index.size > 10:
                                cot_ans += df_to_markdown(item.head(print_rows)) + \
                                           "\nfirst {} rows of {}".format(print_rows, len(item)) + \
                                           "\nthe data above are just slice example, download csv to get full data\n"
                            else:
                                cot_ans += df_to_markdown(item)
                            html_link = pd_to_walker(item)
                            csv_link = pd_to_csv(item)
                            # cot_ans += wrap_html_url_with_markdown_link(html_link)
                            cot_ans += wrap_html_url_with_html_a(html_link)
                            cot_ans += wrap_csv_url_with_html_a(csv_link)
                        elif isinstance(item, str) and is_png_url(item):
                            cot_ans += "\n" + wrap_png_url_with_markdown_image(item) + "\n"
                        elif isinstance(item, str) and is_local_png_path(item):
                            cot_ans += "\n" + wrap_png_url_with_markdown_image(STATIC_URL + item[2:]) + "\n"
                        elif is_iframe_tag(str(item)):
                            cot_ans += "\n" + str(item) + "\n"
                        else:
                            cot_ans += "\n" + str(item) + "\n"
                        print(item)

                    ans = ""
                    # if rag_ans and rag_ans != "":
                    #     ans += "### Base knowledge: \n" + rag_ans + "\n\n"
                    ans += "### Result: \n" + cot_ans + "\n"
                    # print(ans)
                    # review_ans = get_ans_review(question, ans, code)
                    # ans += "## Summarize and review: \n" + review_ans + "\n"

                    logging.info(f"Question: {question}\nAnswer: {ans}\nCode: {code}\n")

                    return ans, code
                except Exception as e:
                    err_msg = "\n" + str(e) + "\n```python\n" + code + "\n```\n"
                    exp = e
                    print(e)
                    continue
    return None, None


def exe_cot_code(code, retries=2, print_rows=5):
    for j in range(retries):
        if code is None:
            continue
        cot_ans = ""
        try:
            result = execute_py_code(code)
            for item in result:
                if item is None:
                    item = " "
                print(item)
                if isinstance(item, pd.DataFrame):
                    if item.index.size > 10:
                        cot_ans += df_to_markdown(item.head(print_rows)) + \
                                   "\nfirst {} rows of {}".format(print_rows, len(item)) + \
                                   "\nthe data above are just slice example, download csv to get full data\n"
                    else:
                        cot_ans += df_to_markdown(item)
                    html_link = pd_to_walker(item)
                    csv_link = pd_to_csv(item)
                    # cot_ans += wrap_html_url_with_markdown_link(html_link)
                    cot_ans += wrap_html_url_with_html_a(html_link)
                    cot_ans += wrap_csv_url_with_html_a(csv_link)
                elif isinstance(item, str) and is_png_url(item):
                    cot_ans += "\n" + wrap_png_url_with_markdown_image(item) + "\n"
                elif isinstance(item, str) and is_iframe_tag(item):
                    html_map = str(item)
                    cot_ans += "\n" + html_map + "\n"
                else:
                    cot_ans += "\n" + str(item) + "\n"

        except Exception as e:
            print("Error:", e)
            if j < retries:
                continue
        # ans = "### Base knowledge: \n" + rag_ans + "\n\n"
        ans = "### Result: \n" + cot_ans + "\n"
        # print(ans)
        return ans
    return None


def get_cot_code(question, retries=2):
    cot_prompt, rag_ans, function_import = get_cot_code_prompt(question)
    print(rag_ans)
    # print(cot_prompt)
    if cot_prompt == "solved":
        return rag_ans, None
    else:
        err_msg = ""
        for j in range(retries):
            code = get_py_code(cot_prompt + err_msg, llm)
            # print(code)
            # code = insert_yield_statements(code)
            code = insert_lines_into_function(code, function_import)
            code = insert_lines_into_function(code, IMPORTANT_MODULE)
            code = insert_lines_into_function(code, THIRD_MODULE)
            print(code)
            if code is None:
                continue
            return code
