# AI Testcase Generator

AI Testcase Generator is a full-stack tool that analyzes source code, generates testcases, runs the code against those testcases using a sandbox compiler, validates the outputs, suggests improved code, and explains failures.

## Features

- Analyze submitted source code
- Detect programming language automatically
- Generate testcases using an LLM
- Execute code using a sandbox compiler platform
- Validate expected output against actual output
- Suggest improved code when testcases fail
- Explain why testcases failed
- Support additional dependency/context files for better testcase generation
- Streamlit-based frontend
- FastAPI-based backend

## Tech Stack

- FastAPI
- Streamlit
- LangGraph
- Groq LLM API
- Judge0 or locally hosted sandbox compiler platform
- Python
- HTTPX
- dotenv

## Project Structure

```text
project-root/
├── main.py
├── frontend.py
├── requirements.txt
├── .env
└── README.md
```

## Setup

Follow the steps below to run the project locally.

### 1. Clone the Repository

```bash
git clone <your-repository-url>
cd <your-project-folder>
```

### 2. Create a Virtual Environment

Create a Python virtual environment:

```bash
python -m venv venv
```

Activate the virtual environment.

For Windows:

```bash
venv\Scripts\activate
```

For macOS/Linux:

```bash
source venv/bin/activate
```

### 3. Install Dependencies

Install all required dependencies:

```bash
pip install -r requirements.txt
```

If you do not have a `requirements.txt` file yet, create one with the following dependencies:

```txt
fastapi
uvicorn
streamlit
requests
httpx
python-dotenv
groq
langgraph
pydantic
```

Then run:

```bash
pip install -r requirements.txt
```

## Environment Variables

Create a `.env` file in the project root directory.

```bash
touch .env
```

For Windows, you can create the file manually or run:

```bash
type nul > .env
```

Add the following variables:

```env
GROQ_API_KEY=your_llm_api_key_here
JUDGE0_PUBLIC_URL=http://localhost:2358
```

Replace the values as needed:

```text
GROQ_API_KEY
Your LLM API key.

JUDGE0_PUBLIC_URL
Your locally hosted sandbox compiler platform URL.
Example: http://localhost:2358
```

## Running the Application

You need to run the backend and frontend in separate terminals.

### 1. Start the Backend

Make sure your virtual environment is activated.

```bash
uvicorn main:app --reload
```

The backend will run at:

```text
http://127.0.0.1:8000
```

### 2. Start the Frontend

Open a new terminal, activate the virtual environment again, and run:

```bash
streamlit run frontend.py
```

The frontend will run at:

```text
http://localhost:8501
```

## Usage

1. Open the Streamlit frontend in your browser.
2. Paste the main code in the main code section.
3. Optionally add dependency/context files such as:
   - middleware files
   - controller files
   - route files
   - validator files
   - service files
   - helper files
4. Click the generate button.
5. The system will:
   - understand the code
   - detect the language
   - generate testcases
   - run the code on the sandbox compiler
   - validate the results
   - suggest improved code
   - explain failures if any

## Important Notes

The main code is the only code executed by the sandbox compiler.

Dependency/context files are used by the AI to better understand the code and generate more accurate testcases. They are not executed directly by the sandbox compiler.

If your main code imports local files, those files must either be included in the executable environment or the code should be adapted into a single-file format for Judge0-style execution.
