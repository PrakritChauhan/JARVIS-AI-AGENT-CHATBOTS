import os
import gradio as gr
from groq import Groq
import json
import smtplib
from dotenv import load_dotenv
import imaplib
from openai import OpenAI
import email
from email.message import EmailMessage
from pprint import pprint

load_dotenv()
groq_api_key = os.getenv("GROQ_API_KEY")
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
openrouter_api_key = os.getenv('OPENROUTER_API_KEY')
EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")
groq = Groq(api_key=groq_api_key)
gemini_via_openai_client = OpenAI(
    api_key=GEMINI_API_KEY,
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
)
openrouter = OpenAI(base_url="https://openrouter.ai/api/v1",
  api_key=openrouter_api_key,)
MODEL = "meta-llama/llama-4-maverick-17b-128e-instruct"
OPENROUTER_MODEL = "openai/gpt-oss-20b:free"
GEMINI_MODEL = "gemini-2.5-flash-lite"
QWEN_MODEL = "qwen/qwen3-coder:free"

emails = []

#secure smtp connetion
IMAP_SERVER = "imap.gmail.com"
#secure imap connection



SYSTEM_PROMPT = """
You're an expert email assistant. You're job is to assist the user in summarizing and replying to their emails.
Your only possible tasks include accessing emails, reading and summarizing emails, replying to emails, and answering general questions. You cannot perform tasks beyond this role.
Give concise answers and perform tasks efficiently. If you don't know the answer, say so.
"""

def get_emails():
    """
        Return a LIST of the last 10 emails as dicts:
        [{message_id, from_email, subject, date, body}, ...]
        """
    global mail
    mail = imaplib.IMAP4_SSL(IMAP_SERVER)
    mail.login(EMAIL, PASSWORD)
    # Always select INBOX (case-insensitive for Gmail, but use 'INBOX')
    typ, _ = mail.select("INBOX")
    if typ != "OK":
        mail.logout()
        raise RuntimeError("Unable to select INBOX")

    # Use UID search + UID fetch consistently
    typ, email_uids_data = mail.uid('search', None, 'ALL')
    if typ != "OK":
        mail.logout()
        raise RuntimeError("IMAP UID search failed")

    uids = email_uids_data[0].split()
    latest_uids = uids[-5:]

    results = []
    for uid in latest_uids:
        typ, msg_data = mail.uid('fetch', uid, '(RFC822)')
        if typ != "OK" or not msg_data or not msg_data[0]:
            continue

        raw_email = msg_data[0][1]
        msg = email.message_from_bytes(raw_email)

        # Extract a plain-text body if possible
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                ctype = part.get_content_type()
                cdisp = str(part.get('Content-Disposition') or "")
                if ctype == 'text/plain' and 'attachment' not in cdisp:
                    payload = part.get_payload(decode=True)
                    if payload:
                        body = payload.decode(errors="ignore")
                        break
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                body = payload.decode(errors="ignore")

        results.append({
            "message_id": msg.get('Message-ID'),
            "from_email": msg.get('From'),
            "subject": msg.get('Subject'),
            "date": msg.get('Date'),
            "body": body
        })

    mail.logout()  # <-- logout AFTER the loop
    return results

def summarize_emails():
    print("in method summarize_emails")
    emails = get_emails()
    SYSTEM_PROMPT = "Youre an expert assistant in summarizing emails. Please provide a concise summary of the emails provided. When refering to the email, provide the number, who it was from, and the content summary."
    SYSTEM_PROMPT += "Provide who the email is from and the summary of the email."
    email_info = ""
    email_count = 1
    email_summaries = ""
    for email in emails:
        email_info += f"{email['from_email']}:\n{email['body']}\n"
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Please provide the summary of the email provided. : {email_info}"},
        ]
        response = groq.chat.completions.create(model=MODEL, messages=messages)
        email_summaries += response.choices[0].message.content
        email_summaries += "\n"
        print(email_summaries)
        email_count += 1
    return emails, email_summaries


def reply_to_email(emails):
    global connection
    connection = smtplib.SMTP('smtp.gmail.com', 587)
    connection.starttls()
    connection.login(EMAIL, PASSWORD)
    SYSTEM_PROMPT = """You're an expert assistant and writer for emails. Please reply to the email given by the user in a concise
    and clear manner. Ensure that the content written is clearly addressed as per the email provided and that the recipient is also addressed.
    Only provide the email body and a salutation as well. 
    """
    if type(emails) == list:
        for email in emails:
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Please reply to this email: \n{email['body']}"},
            ]
            response = openrouter.chat.completions.create(model=OPENROUTER_MODEL, messages=messages)
            msg = EmailMessage()
            msg['From'] = EMAIL
            msg['To'] = email['from_email']
            msg['Subject'] = f"Re: {email['subject']}"
            msg.set_content(f'{response.choices[0].message.content}.')
            msg['In-Reply-To'] = email["message_id"]
            connection.send_message(msg)
    else:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Please reply to this email: \n{emails['body']}"},
        ]
        response = openrouter.chat.completions.create(model=OPENROUTER_MODEL, messages=messages)
        msg = EmailMessage()
        msg['From'] = EMAIL
        msg['To'] = emails['from_email']
        msg['Subject'] = f"Re: {emails['subject']}"
        msg.set_content(f'{response.choices[0].message.content}.')
        msg['In-Reply-To'] = emails["message_id"]
        connection.send_message(msg)

    connection.close()
    if len(email) > 1:
        return("The emails was sent successfully.")
    else:
        return("The email was sent successfully.")

def categorize_question(question):
    Classification_system_prompt = """
    You're job is to categorize the following user question into the one of these categories: summarize emails,
    reply to an email, or send an email, or other. Give one word answers like Summarize, Reply, or other, respectively and perform efficiently. For example,
    if user asks "what emails do I have?", the category will be Summarize. If asked "reply to this email", the category will be Reply.
    **If the question is about replying, provide whether the user is asking to reply to one email or all. If one, provide which email to reply. For example, if user says, "reply to all emails", then category Reply All. 
    If user says "reply to the third email", then category will be" Reply 3". If user says "reply to the tenth email", then category will be "Reply 10". 
    """
    messages = [
        {"role": "system", "content": Classification_system_prompt},
        {"role": "user", "content": question},
    ]
    response = groq.chat.completions.create(model= MODEL, messages= messages)
    print(response.choices[0].message.content)
    return response.choices[0].message.content

classification_function = {
    "name": "categorize_question",
    "description": "Returns the type of query or problem asked by user. Call this whenever you need to access the emails or send emails or reply to an email. For example, if user asks 'What emails do I have', 'reply to this email', or 'Send an email'",
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
    global emails
    tool_call = message.tool_calls[0]
    arguments = json.loads(tool_call.function.arguments)
    question = arguments.get('question')
    classified_question = categorize_question(question)
    if (classified_question == "Summarize"):
        emails, summaries = summarize_emails()
        pprint(emails)
        tool_response = {
            "role": "tool",
            "content": json.dumps({"question": question, "email_summaries": f"Use the following summaries as information:\n{summaries}"}),
            "tool_call_id": tool_call.id
        }
        print(tool_response)
    elif ("Reply" in classified_question):
        if("All" in classified_question):
            print("currently replying to all emails")
            status_message = reply_to_email(emails)
        else:
            print(f"replying to {classified_question.split('Reply')[1]}")
            print(emails[int(classified_question.split("Reply")[1].strip(".").strip()) - 1])
            status_message = reply_to_email(emails[int(classified_question.split("Reply")[1].strip(".").strip()) - 1])
        tool_response = {
            "role": "tool",
            "content": json.dumps({"question": question,
                                   "status_message": f"The response of the api_request is this: {status_message}. Use this to answer is successful or not."}),
            "tool_call_id": tool_call.id
        }
        print(tool_response)
    return tool_response, question



gr.ChatInterface(fn=chat, type="messages").launch()