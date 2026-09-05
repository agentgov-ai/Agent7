


from langchain_community.document_loaders import UnstructuredExcelLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_core.prompts import ChatPromptTemplate
from langchain_huggingface import ChatHuggingFace, HuggingFaceEndpoint, HuggingFaceEmbeddings
from langchain_core.output_parsers import StrOutputParser

from typing import List, Dict, Any
from typing_extensions import TypedDict
from IPython.display import display, Image
import re
import json
import datetime
import os
import sys
from pathlib import Path
from dotenv import load_dotenv


from langgraph.graph import StateGraph, END
EXAMPLE_DIR = Path(__file__).resolve().parent
REPO_ROOT = EXAMPLE_DIR.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

MENU_FILE = EXAMPLE_DIR / "Indian_restaurant_menu_Extract.xlsx"
ORDERS_LOG_FILE = EXAMPLE_DIR / "orders_log.json"
GOVERNANCE_OVERRIDES = EXAMPLE_DIR / "governance-tool-overrides.yaml"
GOVERNANCE_ARTIFACTS = REPO_ROOT / "artifacts" / "governance"

load_dotenv(REPO_ROOT / ".env")
load_dotenv(EXAMPLE_DIR / ".env")
file = str(MENU_FILE)
loader = UnstructuredExcelLoader(file, mode="elements")
data = loader.load()

model_name = "all-MiniLM-L6-v2"
model_kwargs = {'device': 'cpu'}
encode_kwargs = {'normalize_embeddings': False}
hf = HuggingFaceEmbeddings(
    model_name=model_name,
    model_kwargs=model_kwargs,
    encode_kwargs=encode_kwargs
)




db = FAISS.from_documents(data, hf)

print(data[0])

from langchain_huggingface import HuggingFaceEmbeddings

embeddings = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-mpnet-base-v2"

)

from langchain_huggingface import HuggingFaceEmbeddings

text = "Chicken momo"

embedding = hf.embed_query(text)

print(len(embedding))
print(embedding[:10])


from langchain_openai import ChatOpenAI

def get_model():
    model = ChatOpenAI(
        model="qwen/qwen-2.5-7b-instruct",
        api_key= os.environ.get("API_KEY"),
        base_url="https://openrouter.ai/api/v1",
        # OpenRouter serves this model through several providers; some silently
        # drop the `tools` parameter, so the model prints tool calls as text
        # instead of executing them. require_parameters restricts routing to
        # providers that support every request parameter (incl. tools).
        extra_body={"provider": {"require_parameters": True}},
    )
    return model



get_model()

from typing import Optional, List, Dict, Tuple, Any
from pydantic import BaseModel
from langchain.tools import tool, ToolRuntime
from dataclasses import dataclass

class Context(BaseModel):
    Name_User: Optional[str] = None
    Receipt_User: Optional[str] = None


context=Context(Name_User=None, Receipt_User=None)

def greet_customer() -> str:
    """ALWAYS call this tool first before anything else,
    even before get_user_name. This is the very first thing to run."""

    return "Welcome, I will be your waiter. What's your name?"


def get_user_name(runtime: ToolRuntime[Context]) -> str:
  """Call this tool second, right after greet_customer.
     Extract the name from user message.
     Examples: 'myself John' → 'John', 'I am John' → 'John', 'name is John' → 'John'
     Pass the name if user mentioned it in their message.
     If user said something like 'hello' or 'hi' with no name, pass empty string.
     If user said 'I dont want to share' or similar, pass empty string."""

  name = runtime.context.Name_User
  if name:

      return f"Hello {name}, Welcome to our restaurant. How can I help you today?"
  else:
      return "Hello, Welcome to our restaurant How can I help you today?"

def get_menu(query: str) -> str:
    """Call this for ANY food or menu related question from the customer.
    This includes dietary needs, ingredients, prices, recommendations,
    or anything else related to food."""

    results = db.similarity_search(query, k=5)

    if not results:
        return "Sorry, I couldn't find any menu items matching your request."

    menu_info = "\n".join([doc.page_content for doc in results])

    return f"Based on our menu:\n{menu_info}"


def place_order(items: str) -> str:

    """Call this when user wants to order food items.
    ONLY pass items the customer explicitly mentioned.
    NEVER add extra items the customer did not ask for.
    Extract the food items from user message and pass as comma separated string.
    Call this when user says anything like:
    - 'i would like to order'
    - 'i want to order'
    - 'can i get'
    - 'i'll have'
    - 'get me'
    - 'order me all'
    After calling this tool STOP and wait for customer to say yes or no.
    NEVER call confirm_order automatically after this tool."""

    return f"You are ordering: {items}. Would you like to confirm? (yes/no)"

current_order_id = None
def confirm_order(items: str, response: str) -> str:
    """Call this after place_order when customer confirms or denies.
    Pass the same items from place_order.
    Call this when customer says yes or no after being asked to confirm order."""
    global current_order_id

    if response.lower() == "yes":


        import json
        from datetime import datetime
        current_order_id = datetime.now().strftime("%H%M%S")

        order = {
            "order_id": datetime.now().strftime("%H%M%S"),
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "items": items,
            "status": "PENDING STAFF VERIFICATION"
        }

        # save to file
        with ORDERS_LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(order) + "\n")

            print(f"\nOrder ID: {current_order_id} confirmed! Would you like to see your receipt?")
        return ""

    else:
        print("\nYour order has been cancelled. Can I help you with anything else?")
        return ""

def show_receipt(items: str) -> str:
    """Call this when customer asks for receipt or says yes to receipt.
    After calling this tool respond with NOTHING AT ALL.
    Do not add any text after this tool runs."""

    import re

    item_list = [item.strip() for item in items.split(",")]
    subtotal = 0
    receipt_lines = []

    for item in item_list:
        results = db.similarity_search(item, k=1)
        item_text = results[0].page_content if results else ""
        match = re.search(r'\b(\d+)\b', item_text)
        price = int(match.group(1)) if match else 0
        subtotal += price
        receipt_lines.append(f"  {item} - Rs.{price}")

    gst = subtotal * 0.18
    total = subtotal + gst

    print("\n===== YOUR RECEIPT =====")
    print(f"Order ID:  {current_order_id}")
    print("------------------------")
    for line in receipt_lines:
        print(line)
    print("------------------------")
    print(f"Subtotal:  Rs.{subtotal}")
    print(f"GST 18%:   Rs.{gst:.2f}")
    print(f"Total:     Rs.{total:.2f}")
    print("========================")
    print("Thank you for dining with us!")

    return ""

def review_orders():
    """Staff runs this to see all pending orders"""
    import json

    try:
        with ORDERS_LOG_FILE.open("r", encoding="utf-8") as f:
            orders = [json.loads(line) for line in f.readlines()]

        pending = [o for o in orders if o['status'] == "PENDING STAFF VERIFICATION"]

        if not pending:
            print("No pending orders!")
            return

        print("\n===== PENDING ORDERS =====")
        for order in pending:
            print(f"Order ID: {order['order_id']}")
            print(f"Time:     {order['timestamp']}")
            print(f"Items:    {order['items']}")
            print("---")
        print(f"Total pending: {len(pending)}")

    except FileNotFoundError:
        print("No orders yet!")



from langchain.agents import create_agent
from langgraph.checkpoint.memory import MemorySaver
checkpointer = MemorySaver()


SYSTEM_PROMPT = """
You are a restaurant waiter bot. You have ZERO knowledge of your own.

MANDATORY ORDER - follow this EXACTLY:
STEP 1: FIRST message ONLY - call greet_customer then get_user_name
STEP 2: Food/menu questions - ALWAYS call get_menu
STEP 3: Customer orders - ALWAYS call place_order then STOP
STEP 4: ONLY after customer replies yes or no - call confirm_order
STEP 5: Customer asks for receipt - ALWAYS call show_receipt

STRICT RULES:
- NEVER respond without calling a tool first
- NEVER use your own knowledge about food
- NEVER call greet_customer more than once
- NEVER call confirm_order immediately after place_order
- ALWAYS wait for customer to say yes or no before confirm_order
- After show_receipt respond with absolutely nothing
- NEVER generate or show images
- NEVER use markdown image syntax
- NEVER add placeholder images

YOU ARE FORBIDDEN FROM:
- Calling confirm_order without customer saying yes or no
- Adding extra items customer did not ask for
- Adding suggestions after order confirmation
"""

model = get_model()
db = FAISS.from_documents(data, embeddings)

TOOLS = [show_receipt, place_order, greet_customer, get_user_name, get_menu, confirm_order]

agent = create_agent(
    model=get_model(),
    system_prompt=SYSTEM_PROMPT,
    tools=TOOLS,
    context_schema=Context,



)

# Removable governance-evidence layer. Inactive (zero objects created) unless
# GOVERNANCE_EVIDENCE=1 is set. See docs/generated/GOVERNANCE_INSTRUMENTATION.md.
GOVERNANCE = None
if os.environ.get("GOVERNANCE_EVIDENCE") == "1":
    from governance_probe.bootstrap import init_governance
    GOVERNANCE = init_governance(
        tools=TOOLS,
        system_prompt=SYSTEM_PROMPT,
        model_name=getattr(model, "model_name", None),
        model_provider="openrouter",
        overrides_path=GOVERNANCE_OVERRIDES,
        artifacts_dir=GOVERNANCE_ARTIFACTS,
    )

import textwrap

def print_wrapped(text, width=60):
    print("-" * width)
    for line in text.split('\n'):
        if line.strip():
            print(textwrap.fill(line, width=width))
        else:
            print()
    print("-" * width)

def main():
    Mo = get_model()
    print(Mo.invoke("hello").content)

    conversation_history = []
    print(greet_customer())

    config = {"configurable": {"thread_id": "1"}}
    if GOVERNANCE is not None:
        config = GOVERNANCE.merge_invoke_config(config)
    conversation_history = []
    MAX_MESSAGES = 6
    while True:
        user_input = input("\nYou: ")

        if user_input.lower() in ["exit", "quit", "bye"]:
            print("Goodbye! Have a great day!")
            break

        if not user_input.strip():
            print("Waiter: Please say something!")
            continue

        conversation_history.append({"role": "user", "content": user_input})

        if len(conversation_history) > MAX_MESSAGES:
            conversation_history = conversation_history[-MAX_MESSAGES:]

        try:
            response = agent.invoke(
                {"messages": conversation_history},
                config=config,
                context=Context(Name_User=None, Receipt_User=None)
            )

            message = response['messages'][-1].content
            conversation_history.append({"role": "assistant", "content": message})

            if not message or message.strip() == "":
                print("Waiter: Sorry, could you rephrase that?")
            else:
                print("\nWaiter:")
                print_wrapped(message)

        except Exception as e:
            print("Waiter: Sorry, something went wrong. Please try again.")
            print(f"DEBUG: {e}")

    review_orders()


if __name__ == "__main__":
    main()

