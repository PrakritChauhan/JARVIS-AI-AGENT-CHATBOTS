import os, sys
from dotenv import load_dotenv
from groq import Groq
from openai import OpenAI
import google.generativeai
import gradio as gr


load_dotenv(override=True)
openrouter_api_key = os.getenv('OPENROUTER_API_KEY')
gemini_api_key = os.getenv('GEMINI_API_KEY')
groq_api_key = os.getenv("GROQ_API_KEY")
print(openrouter_api_key, gemini_api_key, groq_api_key)

root_dir = os.path.dirname(os.path.abspath(__file__))  # points to the folder of readbot.py
#clients
groq = Groq(api_key=groq_api_key)
openai = OpenAI(
    base_url="https://openrouter.ai/api/v1",
  api_key=openrouter_api_key,
)
gemini_via_openai_client = OpenAI(
    api_key=gemini_api_key,
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
)

#models
LLAMA_3 = "llama-3.3-70b-versatile"
QWEN = "qwen/qwen-2.5-coder-32b-instruct:free"
DEEPSEEK = "deepseek/deepseek-chat-v3-0324:free"
GOOGLE_GEMINI = "gemini-2.5-flash"

system_message = """
You are a helpful assistant for improving code. You're name is Jarvis. You're job is to have expertise in generating code that is much faster.
Give concise and courteous answers if asked a question. 
If asked to improve the code, improve the code to become faster and provide concise and easy-to-understand feedback and
explanation on improvements after the improved code ONLY.
Always be accurate. If you don't know the answer, say so. If the question is anything other than related to code, you don't know the answer.
"""
css = """
chat-box {
    height: 400px;
    overflow-y: scroll;
    border: 1px solid #ccc;
}
"""

def read_code_files(root_dir, extensions=['.py', ".html", ".js", '.java']):
    all_code = ""
    exclude_dirs = {'.venv', 'venv', "env", '__pycache__', '.git', 'site-packages'}
    for subdir, dirs, files in os.walk(root_dir):
        # Dynamically filter out excluded directories during traversal
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        for file in files:
            if file.endswith(tuple(extensions)):
                file_path = os.path.join(subdir, file)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        all_code += f"\n# File: {file_path}\n" + f.read() + "\n"
                except UnicodeDecodeError:
                  print(f"Skipping non-UTF8 file: {file_path}")
    return all_code



def make_user_message(user_message, project_dir):
    user_message = " Read this code to understand it's purpose: \n" + str(read_code_files(project_dir)) + "\n" + user_message
    return user_message

def stream_qwen(messages):
    stream = openai.chat.completions.create(
        model=QWEN,
        messages=messages, stream=True
    )
    reply = ""
    for chunk in stream:
        fragment = chunk.choices[0].delta.content or ""
        reply += fragment
        yield reply.replace('```','')

def stream_deepseek(messages):
    stream = openai.chat.completions.create(model=DEEPSEEK, messages=messages, stream=True)
    reply = ""
    for chunk in stream:
        fragment = chunk.choices[0].delta.content or ""
        reply += fragment
        yield reply.replace('```','')

def stream_llama(messages):
    stream = groq.chat.completions.create(model=LLAMA_3, messages=messages, stream=True)
    reply = ""
    for chunk in stream:
        fragment = chunk.choices[0].delta.content or ""
        reply += fragment
        yield reply.replace('```','')

def stream_gemini(messages):
    stream = gemini_via_openai_client.chat.completions.create(
    model=GOOGLE_GEMINI,
    messages=messages, stream=True
    )
    reply=""
    for chunk in stream:
        fragment = chunk.choices[0].delta.content or ""
        reply += fragment
        yield reply.replace('```','')

def chat(model, user_input, history, project_directory):
    print("chat is launched")
    messages = [{"role": "system", "content": system_message}] + history + [{"role": "user", "content": make_user_message(user_input, project_directory)}]
    print("History is:")
    print(history)
    print("And messages is:")
    print(messages)

    if model=="Qwen":
        bot_reply = stream_qwen(messages)
    elif model=="Google Gemini":
        bot_reply = stream_gemini(messages)
    elif model=="Deepseek-V3":
        bot_reply = stream_deepseek(messages)
    elif model=="Llama 3 70b":
        bot_reply = stream_llama(messages)
    else:
        raise ValueError("Unknown model")
    reply = ""
    for stream_so_far in bot_reply:
        reply = stream_so_far
        yield reply, history

    # Update history
    history.append({"role": "user", "content": user_input})
    history.append({"role": "assistant", "content": reply})

    # Return display string and updated history
    history_display = "\n".join([f"{m['role'].capitalize()}: {m['content']}" for m in history])
    yield history_display, history

# Gradio interface
with gr.Blocks(css=css) as demo:
    with gr.Row():
        project_dir = gr.Textbox(label="Project Directory Path", value="")
    with gr.Row():
        user_message = gr.Textbox(label="User:", lines=10, value="")
        chat_display = gr.Textbox(label="Chatbot:", lines=10)
    with gr.Row():
        model = gr.Dropdown(["Qwen", "Google Gemini", "Deepseek-V3", "Llama 3 70b"], label="Select model", value="Qwen")
        send_btn = gr.Button("Send")
    history_state = gr.State([])
    # Wire the interaction
    send_btn.click(fn=chat, inputs=[model, user_message, history_state, project_dir],
                   outputs=[chat_display, history_state])

demo.launch(inbrowser=True)