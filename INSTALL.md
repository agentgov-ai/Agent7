# 🚀 Installation Guide

Follow these steps to run the Restaurant Agent Bot on your terminal.

---

## Prerequisites
- Python 3.10 or lower recommended (Python 3.14 may cause compatibility warnings)
- pip installed
- Terminal / Command Prompt

---

## Step 1: Download Required Files
Make sure these three files are in the **same folder**:
```
Restaurant_agent1.py
Indian_restaurant_menu_Extract.xlsx
.env                  (you create this in Step 3)
```
> Note: the script currently loads the menu via an **absolute path** at `Restaurant_agent1.py:20`. If your folder differs from `C:\Users\shrey\Downloads\Restaurant_Agent`, update that path.

---

## Step 2: Install All Required Packages
Open terminal, navigate to your folder and run these commands one by one:

```bash
python -m pip install langchain
python -m pip install langchain-community
python -m pip install langchain-openai
python -m pip install langchain-huggingface
python -m pip install langgraph
python -m pip install faiss-cpu
python -m pip install sentence-transformers
python -m pip install unstructured "unstructured[xlsx]"
python -m pip install ipython
python -m pip install openpyxl
python -m pip install python-dotenv
```

Or install everything in one command:
```bash
python -m pip install langchain langchain-community langchain-openai langchain-huggingface langgraph faiss-cpu sentence-transformers unstructured "unstructured[xlsx]" ipython openpyxl python-dotenv
```

---

## Step 3: Add Your API Key
Create a file named `.env` in the same folder as `Restaurant_agent1.py` with this content:
```
API_KEY=your_openrouter_api_key_here
```
Get a free API key at 👉 https://openrouter.ai

⚠️ Save the `.env` file with **UTF-8 encoding**. Do not create it with PowerShell `echo`/`>` redirection — that writes UTF-16, which python-dotenv cannot parse and the key will silently fail to load.

The script loads the key from `.env` at startup (via `python-dotenv`) — do **not** paste the key into the code.

⚠️ **Never commit `.env` to git.** Make sure `.env` is listed in `.gitignore`.

---

## Step 4: Run the Script
```bash
cd path/to/your/folder
python Restaurant_agent1.py
```

### Example (Windows):
```bash
cd C:\Users\yourname\Downloads
python Restaurant_agent1.py
```

### Example (Mac/Linux):
```bash
cd ~/Downloads
python Restaurant_agent1.py
```

---

## Troubleshooting

| Error | Fix |
|---|---|
| `ModuleNotFoundError` | Run `python -m pip install <module-name>` |
| `faiss` not found | Run `python -m pip install faiss-cpu` |
| `getaddrinfo failed` | Check your internet connection |
| API key error / 401 | Check `.env` exists next to the script and contains a valid `API_KEY`; get a fresh key from openrouter.ai if needed |
| `The api_key client option must be set` | `.env` not found, wrong variable name (must be `API_KEY`), or file saved as UTF-16 — re-save as UTF-8 |
| Python not found | Install Python from https://python.org |

---

## Notes
- All packages only need to be installed once
- Every time you want to run the bot just do Step 4
- Make sure the Excel menu file and `.env` are in the same folder as the script
- The script is import-safe: `python Restaurant_agent1.py` starts the chat loop; importing the module does not
