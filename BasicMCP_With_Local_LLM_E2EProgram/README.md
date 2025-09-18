# Basic MCP with Local LLM (Ollama)

This project demonstrates an **end-to-end AI agent** powered by:
- **MCP (Model Context Protocol)** servers and client
- **Ollama** for running a lightweight local LLM
- **REST API tools** (`add_numbers`, `say_hello`)
- **Agent loop** that orchestrates multiple tool calls deterministically

---

## 🚀 Features
- Runs fully **offline** with Ollama (no external API required)
- Supports **both STDIO and HTTP MCP servers**
- JSON-only enforced **LLM outputs**
- **Argument canonicalization** (e.g. `number1/number2` → `a/b`)
- Multi-step orchestration:  
  Example → “Add 12.5 and 7.25, then say hello”  
  Output → `The sum is 19.75. Hello from REST API!`

---

## 📂 Project Structure

BasicMCP_With_Local_LLM_E2EProgram/
├── app/
│ ├── agent/
│ │ ├── llm_agent.py # Main agent loop
│ │ ├── prompts.py # System prompts
│ │ ├── tool_catalog.py # Renders tool descriptions
│ ├── api/
│ │ └── rest_api.py # REST API exposing add_numbers, say_hello
│ ├── mcp/
│ │ ├── mcp_server.py # STDIO MCP server
│ │ ├── mcp_server_http.py # HTTP MCP server
│ │ └── mcp_client_utils.py # Client utilities
│ ├── config/
│ │ ├── settings.yaml # Config for LLM + MCP
│ │ └── logging.yaml # Logging setup
├── requirements.txt
├── README.md
└── tests/ (optional)


---

## ⚙️ Setup

### 1. Clone & Create Virtual Env
```powershell
git clone <your-repo-url>
cd BasicMCP_With_Local_LLM_E2EProgram
python -m venv .venv
.venv\Scripts\Activate.ps1   # Windows
# source .venv/bin/activate  # Linux/Mac

2. Install Requirements
pip install --upgrade pip
pip install -r requirements.txt

3. Install Ollama (if not already)

Download Ollama

Pull models:

ollama pull tinyllama
ollama pull llama3.2:3b-instruct-q4_K_M

▶️ Run
Step 1. Start REST API
python app/api/rest_api.py
# runs at http://127.0.0.1:8000

Step 2. Run MCP STDIO server
python app/mcp/mcp_server.py

Step 3. Run Agent
python -m app.agent.llm_agent "Add 12.5 and 7.25, then say hello."


Expected:

The sum is 19.75. Hello from REST API!

📬 Test with Postman

Use the included collection BasicMCP_Agent.postman_collection.json.

Endpoints:

GET http://127.0.0.1:8000/hello

POST http://127.0.0.1:8000/add_numbers

{
  "a": 12.5,
  "b": 7.25
}

🖼 Diagram
flowchart TD
    U[User Prompt] --> A[LLM Agent]
    A -->|Tool Call: add_numbers| M1[REST API add_numbers]
    M1 -->|Result: 19.75| A
    A -->|Tool Call: say_hello| M2[REST API say_hello]
    M2 -->|Result: "Hello from REST API!"| A
    A -->|Final Answer| U

✅ Example Prompts
python -m app.agent.llm_agent "Add 100 and 50, then say hello."
# The sum is 150. Hello from REST API!

🛠 Troubleshooting

Ensure Ollama is running: ollama list

Verify REST API: Invoke-RestMethod http://127.0.0.1:8000/hello

Always activate venv before running.

📌 Notes

The system is modular: you can plug in new tools into rest_api.py and they’ll automatically be available to the agent.

By default, the agent uses tinyllama. Configure in app/config/settings.yaml.


---

# 📂 Postman Collection (BasicMCP_Agent.postman_collection.json)

```json
{
  "info": {
    "name": "Basic MCP Agent",
    "_postman_id": "12345678-abcd-efgh-ijkl-9876543210",
    "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
  },
  "item": [
    {
      "name": "Hello Endpoint",
      "request": {
        "method": "GET",
        "header": [],
        "url": {
          "raw": "http://127.0.0.1:8000/hello",
          "protocol": "http",
          "host": ["127.0.0.1"],
          "port": "8000",
          "path": ["hello"]
        }
      }
    },
    {
      "name": "Add Numbers",
      "request": {
        "method": "POST",
        "header": [
          { "key": "Content-Type", "value": "application/json" }
        ],
        "body": {
          "mode": "raw",
          "raw": "{\n  \"a\": 12.5,\n  \"b\": 7.25\n}"
        },
        "url": {
          "raw": "http://127.0.0.1:8000/add_numbers",
          "protocol": "http",
          "host": ["127.0.0.1"],
          "port": "8000",
          "path": ["add_numbers"]
        }
      }
    }
  ]
}


📌 You can commit these into your repo as:

README.md

docs/BasicMCP_Agent.postman_collection.json

docs/diagram.mmd (mermaid source) or export as PNG

👉 Do you want me to also generate a PNG diagram (ready-to-use image) from the Mermaid above so you can directly insert into your PPT/LinkedIn?