import os, json
from datetime import datetime
import time
from dotenv import load_dotenv
from markdown_it.common.html_blocks import block_names
from notion_client import Client
from openai import OpenAI
from groq import Groq
import gradio as gr
from pprint import pprint

load_dotenv()
NOTION_TOKEN = os.getenv('NOTION_TOKEN')
OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY_PA')
GROQ_API_KEY = os.getenv('GROQ_API_KEY')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

QWEN_MODEL = "deepseek/deepseek-chat-v3-0324:free"
GPT_MODEL = "openai/gpt-oss-20b"
GEMMA_MODEL = "google/gemma-3-27b-it:free"
META_MODEL = "meta-llama/llama-4-maverick-17b-128e-instruct"
GEMINI_MODEL = "gemini-2.5-flash-lite"

notion = Client(auth=NOTION_TOKEN)
client = OpenAI(base_url="https://openrouter.ai/api/v1",
  api_key=OPENROUTER_API_KEY,)
groq = Groq(api_key=GROQ_API_KEY)
gemini_via_openai_client = OpenAI(
    api_key=GEMINI_API_KEY,
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
)


SYSTEM_PROMPT = """
You're an expert notion assistant. You're job is to answer questions or perform tasks provided by the user based on the information from Notion.
Your only possible tasks include answering questions regarding schedule, making changes to a schedule, and answering general questions. You cannot perform tasks beyond this role.
Give concise answers and perform tasks efficiently. If you don't know the answer, say so.
"""


def get_schedule():
    # daily_schedule_template
    dst_headings = notion.blocks.children.list(block_id="21971ecf0ca080f4bf5eebb6539eb5df")
    dst_schedule_id = dst_headings["results"][0]["id"]
    dst_s = notion.blocks.children.list(block_id=dst_schedule_id)
    dst_schedule = {}
    block_ids = {}
    for block in dst_s["results"]:
        if block["table_row"]["cells"][0][0]["plain_text"] != "Time":
            block_ids[block["table_row"]["cells"][0][0]["plain_text"]] = block["id"]
        try:
            time_label = block["table_row"]["cells"][0][0]["plain_text"]
            activity_label = block["table_row"]["cells"][1][0]["plain_text"]
            note_label = block["table_row"]["cells"][2][0]["plain_text"]
            dst_schedule[time_label] = {
                activity_label: note_label}
        except IndexError:
            if activity_label == "":
                dst_schedule[time_label] = {
                    "Empty": "No notes"}
            else:
                dst_schedule[time_label] = {
                    activity_label: "No notes"}
    print("Schedule\n")
    print(dst_schedule)
    return dst_schedule, block_ids

def find_prev_block(task_time, block_ids):
    key_iterator = iter(block_ids.keys())
    current_key = next(key_iterator)
    print(task_time)
    for r in range(len(block_ids) - 1):
        next_key = next(key_iterator)
        print(next_key)
        if(len(current_key) > 8):
            current_key = current_key[-8:]
        if(len(next_key) > 8):
            next_key = next_key[-8:]
        print(current_key, next_key)
        time_obj1 = datetime.strptime(current_key.strip(), "%I:%M %p").time()
        time_obj2 = datetime.strptime(next_key.strip(), "%I:%M %p").time()
        time_obj3 = datetime.strptime(task_time.strip(), "%I:%M %p").time()
        if time_obj1 <= time_obj3 < time_obj2:
            return block_ids[current_key]
        current_key = next_key

def comprehend(question):
    system_prompt = """
    You're job is to analyze the given question as return and extract the following information: Task, Time_range, Activity, and Notes.
    The task is what is supposed to be done: adding a task, where you will return Add, or update a task, where you will return Update. The Time_range is how long the activity will be, either explicitly listed, for exmaple "6:10 AM - 6:25 AM" or implicitly listed
    , for example a 15 minute break after 7:00 AM, which means you will return "7:00 AM - 7:15 AM". The activity will be what
    the user will do and the notes will be any extra info related to this activity. Return a JSON object in the following format:
    {
        "Task": Task,
        "Time":Time_range,
        "Activity":Activity,
        "Notes":Notes
    }
    """
    response = groq.chat.completions.create(model=GPT_MODEL, messages= [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": question}
    ], response_format={"type": "json_object"})
    #print((response.choices[0].message.content).strip("```"))
    content = json.loads((response.choices[0].message.content))
    task = content["Task"]
    task_time = content["Time"]
    activity = content["Activity"]
    notes = content["Notes"]
    return task, task_time, activity, notes

def update_schedule(task, task_time, activity, notes):
    user_schedule, block_ids = get_schedule()
    print((task_time[:8]))
    prev_block_id = find_prev_block(task_time[:8], block_ids)
    if task == "Add":
        print("adding")
        try:
            print("sending request")
            response = notion.blocks.children.append(block_id="21971ecf0ca080d7aeefda4b1b5ae9b1", children=[{"object": "block", "type": "table_row", "table_row": {"cells": [
            [{"text": {"content": task_time}}],
            [{"text": {"content": activity}}],
            [{"text": {"content": notes}}]]}}], after=prev_block_id)
            print(response)
            return("The task has been added to the schedule successfully.")
        except Exception as e:
            print(e)
            return("An issue has occurred while adding the task.")

def categorize_question(question):
    Classification_system_prompt = """
    You're job is to categorize the following user question into the one of these categories: Answer a question based on notion information,
    add information to notion, or other. Give one word answers like Answer, Update, or Other, respectively and perform efficiently. For example,
    if user asks "what do I have to complete today?", the category will be Answer. If asked "add this task to schedule", the category will be Update.
    """
    messages = [
        {"role": "system", "content": Classification_system_prompt},
        {"role": "user", "content": question},
    ]
    response = groq.chat.completions.create(model= GPT_MODEL, messages= messages)
    print(response.choices[0].message.content)
    return response.choices[0].message.content

classification_function = {
    "name": "categorize_question",
    "description": "Returns the type of query or problem asked by user. Call this whenever you need to know the schedule and if user asks questions regarding schedule or updating schedule, for example if user asks 'What tasks do I have at 1:00 PM' or 'Can you add calling James at 2:00 PM to my schedule'",
    "parameters": {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "The question asked by the user",
            },
        },
        "required": ["question"],
        "additionalProperties": False
    }
}
tools = [{"type": "function", "function": classification_function}]


def chat(message, history):
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history + [{"role": "user", "content": message}]
    response = gemini_via_openai_client.chat.completions.create(model=GEMINI_MODEL, messages=messages, tools=tools)
    if response.choices[0].finish_reason == "tool_calls":
        print("here")
        message = response.choices[0].message
        response, city = handle_tool_call(message)
        messages.append(message)
        messages.append(response)
        response = gemini_via_openai_client.chat.completions.create(model=GEMINI_MODEL, messages=messages)

    return response.choices[0].message.content

def handle_tool_call(message):
    tool_call = message.tool_calls[0]
    arguments = json.loads(tool_call.function.arguments)
    question = arguments.get('question')
    classified_question = categorize_question(question)
    if (classified_question == "Answer"):
        print("currently here")
        user_schedule, block_ids = get_schedule()
        pprint(user_schedule)
        response = {
            "role": "tool",
            "content": json.dumps({"question": question, "user_schedule": f"Use the following schedule as information:\n{user_schedule}"}),
            "tool_call_id": tool_call.id
        }
        pprint(response)
    elif (classified_question == "Update"):
        print("currently updating")
        task, task_time, activity, notes = comprehend(question)
        status_message = update_schedule(task, task_time, activity, notes)
        response = {
            "role": "tool",
            "content": json.dumps({"question": question,
                                   "status_message": f"The response of the api_request is this: {status_message}. Use this to answer is successful or not."}),
            "tool_call_id": tool_call.id
        }
    return response, question


gr.ChatInterface(fn=chat, type="messages").launch()
#
# #schedule
# headings = notion.blocks.children.list(block_id="22971ecf0ca080959555ee7424560b26")
# #schedules_ids = [block['id'] for block in headings["results"] if block["has_children"] == True]
# schedules_ids = {block["heading_2"]["rich_text"][0]["text"]["content"]:headings["results"][headings["results"].index(block) + 1]["id"] for block in headings["results"] if "heading_2" in block}
# schedule = {}
# for key, value in schedules_ids.items():
#     s = notion.blocks.children.list(block_id=value)
#     for block in s["results"]:
#         if block["table_row"]["cells"][0][0]["plain_text"] != "Time":
#             schedule[block["table_row"]["cells"][0][0]["plain_text"]] = {block["table_row"]["cells"][1][0]["plain_text"]: block["table_row"]["cells"][2][0]["plain_text"]}
#

#daily_schedule_template
dst_headings =  notion.blocks.children.list(block_id="21971ecf0ca080f4bf5eebb6539eb5df")
dst_schedule_id = dst_headings["results"][0]["id"]
dst_s = notion.blocks.children.list(block_id=dst_schedule_id)
pprint(dst_s)
dst_schedule = {}
for block in dst_s["results"]:
    try:
        dst_schedule[block["table_row"]["cells"][0][0]["plain_text"]] = {
        block["table_row"]["cells"][1][0]["plain_text"]: block["table_row"]["cells"][2][0]["plain_text"]}
    except IndexError:
        dst_schedule[block["table_row"]["cells"][0][0]["plain_text"]] = {
            "Empty": "No notes"}

#Content_Planner (tbd later)
# db_1 = notion.databases.query(database_id="23b71ecf0ca08069b970effb7e3584a5")
# Content_db = {}
# for result in db_1["results"]:
#
#
# pprint(Content_db)

