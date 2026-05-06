from typing import Optional, List

import httpx
from pywebio.session import set_env
from pywebio.input import input, TEXT, textarea, file_upload, select, checkbox
from pywebio.output import put_text, put_html, put_markdown, clear, put_loading, toast, popup, put_buttons, \
    put_collapse, put_table
from pywebio import start_server, config

from data_access.read_db import get_rows_from_all_tables, get_table_comments_dict
from utils.get_config import config_data
import base64

SELECT_TABLES = []
SELECT_LABELS = []


def ai_agent_api(question: str, tables: Optional[List[str]] = None, path: str = "/api/ask-agent/",
                 url="http://127.0.0.1:" + str(config_data["server_port"])):
    # Use httpx to send a request to the /ask-agent/ endpoint of another server
    with httpx.Client(timeout=180.0) as client:
        try:
            payload = {"question": question}
            if tables:
                payload["tables"] = tables

            response = client.post(url + path, json=payload)
            # Check response status code
            if response.status_code == 200:
                print(response.json()["ans"])
                return response.json()["ans"], response.json()["code"]
            else:
                return None
        except httpx.RequestError as e:
            print(e)
            # Handle request error
            return None


def upload_csv_api(file_content, table_name="uploaded_data"):
    url = f"http://127.0.0.1:{config_data['server_port']}/upload-csv/"
    files = {
        'file': ('data.csv', file_content, 'text/csv')
    }
    data = {
        'table_name': table_name
    }
    with httpx.Client(timeout=30.0) as client:
        try:
            response = client.post(url, files=files, data=data)
            if response.status_code == 200:
                return response.json()
            else:
                return {"error": f"{response.status_code}", "details": response.text}
        except httpx.RequestError as e:
            return {"error": f"{str(e)}"}


def upload_doc_api(file_content, filename, table_name="uploaded_data"):
    url = f"http://127.0.0.1:{config_data['server_port']}/upload-txt/"
    files = {
        'file': (filename, file_content, 'application/octet-stream')
    }
    data = {
        'table_name': table_name
    }
    with httpx.Client(timeout=30.0) as client:
        try:
            response = client.post(url, files=files, data=data)
            if response.status_code == 200:
                return response.json()
            else:
                return {"error": f"{response.status_code}", "details": response.text}
        except httpx.RequestError as e:
            return {"error": f"{str(e)}"}


def handle_csv_upload():
    file_info = file_upload(
        "Please select a CSV file to upload",
        accept=".csv",
        help_text="Select the CSV file you want to upload"
    )

    if file_info:
        table_name = input("Enter table name (optional, default is 'uploaded_data')", type=TEXT,
                           placeholder="uploaded_data", required=False)
        if not table_name:
            table_name = "uploaded_data"
        with put_loading(shape="grow", color="primary"):
            result = upload_csv_api(file_info['content'], table_name)
            print(result)
        err = result.get('type', "error")
        if err == "error":
            toast(f"Upload failed: {result}", color='error')
        else:
            toast("File uploaded successfully!", color='success')
            put_markdown("### Upload Results")
            put_markdown(f"Table name: `{result.get('table_name', table_name)}`")
            put_markdown(f"Row count: {result.get('row_count', 'N/A')}")
            put_markdown(f"Message: {result.get('message', 'N/A')}")


def handle_doc_upload():
    file_info = file_upload(
        "Please select a document file to upload (txt, doc, docx, pdf)",
        accept=".txt,.doc,.docx,.pdf",
        help_text="Select the document file you want to upload"
    )

    if file_info:
        table_name = input("Enter table name (optional, default is 'uploaded_data')", type=TEXT,
                           placeholder="uploaded_data", required=False)
        if not table_name:
            table_name = "uploaded_data"
        with put_loading(shape="grow", color="primary"):
            result = upload_doc_api(file_info['content'], file_info['filename'], table_name)
            print(result)

        if result.get('error'):
            toast(f"Upload failed: {result.get('error')}", color='error')
        else:
            toast("File uploaded successfully!", color='success')
            put_markdown("### Upload Results")
            put_markdown(f"Table name: `{result.get('table_name', table_name)}`")
            put_markdown(f"Extracted text length: {result.get('extracted_text_length', 'N/A')}")
            put_markdown(f"Preview: {result.get('preview', 'N/A')}")


def handle_table_selection(table_options):
    global SELECT_TABLES, SELECT_LABELS
    checkbox_options = [(opt['label'], opt['value']) for opt in table_options]
    selected_tables = checkbox(
        "Select tables: ",
        options=checkbox_options,
        inline=True
    )
    SELECT_TABLES = selected_tables
    put_markdown(f"You have selected: `{', '.join(selected_tables)}`")
    if selected_tables:
        selected_labels = []
        for table_value in selected_tables:
            for opt in table_options:
                if opt['value'] == table_value:
                    selected_labels.append(opt['label'])
                    break
        SELECT_LABELS = selected_labels


# @config(theme="dark")
def main():
    global SELECT_TABLES, SELECT_LABELS
    put_markdown("# Data-Copilot")
    # set_env(output_max_width='90%')
    # # Load HTML content
    # with open("DatasetExplorer.html", 'r', encoding='utf-8') as file:
    #     html_content = file.read()
    # put_html(html_content)
    first_five_rows = get_rows_from_all_tables()
    # print(first_five_rows)

    table_comments = get_table_comments_dict()
    table_options = []
    for table_name, comment in table_comments.items():
        display_name = f"{table_name} ({comment})" if comment else table_name
        table_options.append({'label': display_name, 'value': table_name})

    # 添加表格选择和上传按钮
    put_buttons(['Select Tables', 'Upload CSV File', 'Upload Document File'],
                onclick=[lambda: handle_table_selection(table_options), handle_csv_upload, handle_doc_upload])

    with put_collapse(f"Tables"):
        for table_name, rows in first_five_rows.items():
            with put_collapse(f"table {table_name}"):
                put_text(f"table {table_name} first 5 rows:")
                put_table([rows.columns.tolist()] + rows.values.tolist())

    conversation_history = []

    question = textarea("Enter your question here:", type=TEXT, rows=2)
    put_markdown("## " + question)
    conversation_history.append(f"Q: {question}")
    with put_loading():
        step_str, _ = ai_agent_api(question, SELECT_TABLES, "/api/step-chat/")
    if step_str:
        step_str = textarea("revise plan:", type=TEXT, rows=2, value=step_str)
        conversation_history.append(f"Planner: {step_str}")
        put_markdown(step_str, sanitize=False)
    else:
        put_text("Failed to get a response from the AI Agent.")

    while True:
        table_pre = ""
        # if SELECT_TABLES != []:
        #     table_pre = "use table:" + str(SELECT_TABLES) + " only!!! \n" + str(SELECT_LABELS) + "\n"

        value = "please do the next(or first) step to do on the list"
        question = textarea("Check the todo list:", value=value, type=TEXT, rows=2)
        put_markdown("## " + question)
        if conversation_history:
            # context = "\n".join(conversation_history[-4:])
            context = "\n".join(conversation_history)
            full_question = f"Context:\n{context}\n\nCurrent Question:\n{question}"
        else:
            full_question = question

        if value == question:
            with put_loading():
                response, code = ai_agent_api(table_pre + full_question, SELECT_TABLES, "/api/ask-agent/")
            if response:
                conversation_history.append(f"Q: {question}")
                conversation_history.append(f"Code Generated: {code}")
                conversation_history.append(f"Exe Result: {response}")
                put_markdown(response, sanitize=False)
            else:
                put_text("Failed to get a response from the AI Agent.")

            context = "\n".join(conversation_history)
            full_question = f"Context:\n{context}\n"
        else:
            context = "\n".join(conversation_history)
            full_question = f"Context:\n{context}\n\nCurrent Question:\n{question}"

        with put_loading():
            step_str, _ = ai_agent_api(table_pre + full_question, SELECT_TABLES, "/api/step-chat/")
        if step_str:
            step_str = textarea("revise plan:", type=TEXT, rows=2, value=step_str)
            conversation_history.append(f"Planner: {step_str}")
            put_markdown(step_str, sanitize=False)
        else:
            put_text("Failed to get a response from the AI Agent.")


if __name__ == '__main__':
    start_server(main, port=8037, debug=True)
