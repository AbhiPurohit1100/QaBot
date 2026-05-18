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

JUDGE0_URL = os.getenv("JUDGE0_PUBLIC_URL")

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

    original_code: str

    understanding: str

    raw_testcase_response: str

    testcases: List[Dict[str, Any]]

    judge0_results: List[Dict[str, Any]]

    validated_results: List[Dict[str, Any]]

    score: int

    improved_code: str

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
1. 10 testcases
2. Include normal + edge cases
3. Each testcase must contain:
   - stdin
   - expected_stdout
4. It should include all edge cases like x/0 or null pointer dereferencing etc etc
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
IMPROVEMENT_PROMPT = """
You are an expert competitive programming code improvement agent.

The user's code was executed against generated testcases using Judge0.

Your job:
1. Read the problem understanding.
2. Read the original code.
3. Read all generated testcases.
4. Read Judge0 execution results.
5. Read validation results showing PASS/FAIL.
6. Suggest one better corrected version of the code.
7. Preserve the same input/output format.
8. Return ONLY the full corrected code.
9. Do not explain anything.
10. Do not use markdown.

Important:
- Do not assume the suggested code will be re-tested.
- Your output must be the best final suggested code based on the available results.
- If the original code already passes all testcases, still return the original code unchanged.

Problem Understanding:
{understanding}

Original Code:
{code}

Generated Testcases:
{testcases}

Judge0 Results:
{judge0_results}

Validated Results:
{validated_results}
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


def clean_code_response(text: str):

    text = text.strip()

    text = re.sub(
        r"^```[a-zA-Z]*",
        "",
        text
    ).strip()

    text = re.sub(
        r"```$",
        "",
        text
    ).strip()

    return text
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


def improvement_agent(state: GraphState):

    prompt = IMPROVEMENT_PROMPT.format(
        understanding=state["understanding"],
        code=state["original_code"],
        testcases=json.dumps(
            state["testcases"],
            indent=2
        ),
        judge0_results=json.dumps(
            state["judge0_results"],
            indent=2
        ),
        validated_results=json.dumps(
            state["validated_results"],
            indent=2
        )
    )

    improved_code = invoke_llm(prompt)

    improved_code = clean_code_response(improved_code)

    return {
        "improved_code": improved_code
    }

    current_score = state["score"]
    total = len(state["validated_results"])

    iteration = state.get("iteration", 0)

    # If already passed all testcases, stop improving
    if current_score == total:

        return {
            "improved_code": state["code"],
            "iteration": iteration
        }

    # If already tried 2 times, stop
    if iteration >= 2:

        return {
            "improved_code": state["code"],
            "iteration": iteration
        }

    failed_results = [
        result for result in state["validated_results"]
        if not result["passed"]
    ]

    prompt = IMPROVEMENT_PROMPT.format(
        understanding=state["understanding"],
        code=state["code"],
        results=json.dumps(
            failed_results,
            indent=2
        )
    )

    improved_code = invoke_llm(prompt)

    improved_code = clean_code_response(improved_code)

    return {
        "code": improved_code,
        "improved_code": improved_code,
        "iteration": iteration + 1
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

    graph.add_node(
        "improvement_agent",
        improvement_agent
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
        "improvement_agent"
    )

    graph.add_edge(
        "improvement_agent",
        END
    )

    return graph.compile()

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

    graph.add_node(
        "improvement_agent",
        improvement_agent
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

    graph.add_conditional_edges(
        "validation_agent",
        should_continue_improving,
        {
            "retry": "improvement_agent",
            "end": END
        }
    )

    graph.add_edge(
        "improvement_agent",
        "judge0_agent"
    )

    return graph.compile()

workflow = build_graph()
# =====================================
# ROUTE
# =====================================

@app.post("/generate-testcases")
def generate_testcases(req: CodeRequest):

    result = workflow.invoke({
        "code": req.code,
        "original_code": req.code,
        "improved_code": req.code
    })

    return {

        "success": True,

        "score":
            result["score"],

        "total_testcases":
            len(result["validated_results"]),

        "original_code":
            result["original_code"],

        "improved_code":
            result.get(
                "improved_code",
                result["original_code"]
            ),

        "results":
            result["validated_results"]
    }

    result = workflow.invoke({
        "code": req.code,
        "original_code": req.code,
        "iteration": 0,
        "improved_code": req.code
    })

    return {

        "success": True,

        "score":
            result["score"],

        "total_testcases":
            len(result["validated_results"]),

        "iterations_used":
            result.get("iteration", 0),

        "original_code":
            result["original_code"],

        "improved_code":
            result.get("improved_code", result["code"]),

        "results":
            result["validated_results"]
    }