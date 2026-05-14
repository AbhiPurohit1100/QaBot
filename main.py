from fastapi import FastAPI
from pydantic import BaseModel

from typing import TypedDict, List, Dict, Any

from langgraph.graph import StateGraph, END

from groq import Groq
from dotenv import load_dotenv

import os
import json
import re
import httpx
import base64
import time

# =====================================
# ENV
# =====================================

load_dotenv()

http_client = httpx.Client(
    verify=False,
    timeout=120.0
)

client = Groq(
    api_key=os.getenv("GROQ_API_KEY"),
    http_client=http_client
)

MODEL_NAME = "openai/gpt-oss-120b"

JUDGE0_URL = JUDGE0_PUBLIC_URL

# =====================================
# FASTAPI
# =====================================

app = FastAPI()

# =====================================
# REQUEST MODEL
# =====================================

class CodeRequest(BaseModel):
    code: str

# =====================================
# GRAPH STATE
# =====================================

class GraphState(TypedDict):

    code: str

    understanding: str

    raw_testcase_response: str

    testcases: List[Dict[str, Any]]

    judge0_results: List[Dict[str, Any]]

    validated_results: List[Dict[str, Any]]

    score: int

# =====================================
# LANGUAGE MAP
# =====================================

LANGUAGE_MAP = {
    "java": 62,
    "python": 71,
    "cpp": 54,
    "c++": 54
}

# =====================================
# PROMPTS
# =====================================

UNDERSTANDING_PROMPT = """
You are an expert competitive programming analyst.

Analyze the following code and infer:
1. What problem it solves
2. Input format
3. Output format
4. Important edge cases

CODE:
{code}
"""

TESTCASE_PROMPT = """
You are an expert testcase generator.

Based on the following understanding:

{understanding}

Generate:
1. 6 testcases
2. Include normal + edge cases
3. Each testcase must contain:
   - stdin
   - expected_stdout

Return STRICT JSON ONLY.

Example:

[
  {{
    "stdin": "5 7",
    "expected_stdout": "12"
  }}
]
"""

VALIDATION_PROMPT = """
You are a testcase validation agent.

Expected Output:
{expected}

Actual Output:
{actual}

Determine if both are logically equivalent.

Return ONLY:
PASS
or
FAIL
"""

# =====================================
# HELPERS
# =====================================

def invoke_llm(prompt: str):

    completion = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ],
        temperature=0.1,
        max_completion_tokens=4096,
        top_p=1,
        reasoning_effort="medium",
        stream=False
    )

    return completion.choices[0].message.content.strip()

def extract_json(text: str):

    match = re.search(
        r"\[\s*{.*}\s*\]",
        text,
        re.DOTALL
    )

    if not match:
        raise Exception(
            "Could not extract JSON from response"
        )

    return json.loads(match.group())

def detect_language(code: str):

    if "public class" in code:
        return "java"

    if "#include" in code:
        return "cpp"

    return "python"

# =====================================
# AGENTS
# =====================================

def context_agent(state: GraphState):

    prompt = UNDERSTANDING_PROMPT.format(
        code=state["code"]
    )

    understanding = invoke_llm(prompt)

    return {
        "understanding": understanding
    }

def testcase_agent(state: GraphState):

    prompt = TESTCASE_PROMPT.format(
        understanding=state["understanding"]
    )

    response = invoke_llm(prompt)

    return {
        "raw_testcase_response": response
    }

def parser_agent(state: GraphState):

    testcases = extract_json(
        state["raw_testcase_response"]
    )

    return {
        "testcases": testcases
    }

# =====================================
# JUDGE0 AGENT
# =====================================

def judge0_agent(state: GraphState):

    code = state["code"]

    language = detect_language(code)

    language_id = LANGUAGE_MAP[language]

    submissions = []

    for tc in state["testcases"]:

        submissions.append({

            "language_id": language_id,

            "source_code": base64.b64encode(
                code.encode()
            ).decode(),

            "stdin": base64.b64encode(
                tc["stdin"].encode()
            ).decode(),

            "cpu_time_limit": 2,

            "memory_limit": 128000
        })

    # =====================================
    # SUBMIT BATCH
    # =====================================

    response = httpx.post(
        f"{JUDGE0_URL}/submissions/batch?base64_encoded=true",

        json={
            "submissions": submissions
        },

        timeout=30
    )

    data = response.json()

    print("\n=========== SUBMISSION RESPONSE ===========")
    print(json.dumps(data, indent=2))

    tokens = []

    for item in data:

        token = item.get("token")

        if token:
            tokens.append(token)

    if not tokens:

        raise Exception(
            "No Judge0 tokens received"
        )

    # =====================================
    # POLLING
    # =====================================

    completed = False

    final_results = None

    for _ in range(20):

        token_string = ",".join(tokens)

        result_response = httpx.get(
            f"{JUDGE0_URL}/submissions/batch",

            params={
                "tokens": token_string,
                "base64_encoded": "true"
            },

            timeout=30
        )

        result_data = result_response.json()

        print("\n=========== POLLING RESPONSE ===========")
        print(json.dumps(result_data, indent=2))

        submissions_data = result_data.get(
            "submissions",
            []
        )

        all_done = True

        for sub in submissions_data:

            status_obj = sub.get("status")

            if not status_obj:

                all_done = False
                break

            status_id = status_obj.get("id")

            # 1 -> In Queue
            # 2 -> Processing

            if status_id in [1, 2]:

                all_done = False
                break

        if all_done:

            completed = True
            final_results = submissions_data
            break

        time.sleep(1)

    # =====================================
    # TIMEOUT
    # =====================================

    if not completed:

        raise Exception(
            "Judge0 execution timeout"
        )

    # =====================================
    # PARSE RESULTS
    # =====================================

    results = []

    for idx, result in enumerate(final_results):

        print("\n=========== SINGLE RESULT ===========")
        print(json.dumps(result, indent=2))

        stdout = ""

        if result.get("stdout"):

            try:

                stdout = base64.b64decode(
                    result["stdout"]
                ).decode().strip()

            except:
                stdout = result["stdout"]

        stderr = ""

        if result.get("stderr"):

            try:

                stderr = base64.b64decode(
                    result["stderr"]
                ).decode().strip()

            except:
                stderr = result["stderr"]

        compile_output = ""

        if result.get("compile_output"):

            try:

                compile_output = base64.b64decode(
                    result["compile_output"]
                ).decode().strip()

            except:
                compile_output = result["compile_output"]

        results.append({

            "stdin":
                state["testcases"][idx]["stdin"],

            "expected_output":
                state["testcases"][idx]["expected_stdout"],

            "actual_output":
                stdout,

            "stderr":
                stderr,

            "compile_output":
                compile_output,

            "status":
                result.get("status", {}).get(
                    "description",
                    "Unknown"
                )
        })

    return {
        "judge0_results": results
    }

# =====================================
# VALIDATION AGENT
# =====================================

def validation_agent(state: GraphState):

    validated = []

    score = 0

    for tc in state["judge0_results"]:

        expected = tc["expected_output"].strip()

        actual = tc["actual_output"].strip()

        if expected == actual:

            passed = True

        else:

            prompt = VALIDATION_PROMPT.format(
                expected=expected,
                actual=actual
            )

            result = invoke_llm(prompt)

            passed = "PASS" in result

        if passed:
            score += 1

        validated.append({
            **tc,
            "passed": passed
        })

    return {
        "validated_results": validated,
        "score": score
    }

# =====================================
# LANGGRAPH
# =====================================

def build_graph():

    graph = StateGraph(GraphState)

    graph.add_node(
        "context_agent",
        context_agent
    )

    graph.add_node(
        "testcase_agent",
        testcase_agent
    )

    graph.add_node(
        "parser_agent",
        parser_agent
    )

    graph.add_node(
        "judge0_agent",
        judge0_agent
    )

    graph.add_node(
        "validation_agent",
        validation_agent
    )

    graph.set_entry_point(
        "context_agent"
    )

    graph.add_edge(
        "context_agent",
        "testcase_agent"
    )

    graph.add_edge(
        "testcase_agent",
        "parser_agent"
    )

    graph.add_edge(
        "parser_agent",
        "judge0_agent"
    )

    graph.add_edge(
        "judge0_agent",
        "validation_agent"
    )

    graph.add_edge(
        "validation_agent",
        END
    )

    return graph.compile()

workflow = build_graph()

# =====================================
# ROUTE
# =====================================

@app.post("/generate-testcases")
def generate_testcases(req: CodeRequest):

    result = workflow.invoke({
        "code": req.code
    })

    return {

        "success": True,

        "score":
            result["score"],

        "total_testcases":
            len(result["validated_results"]),

        "results":
            result["validated_results"]
    }