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

if not JUDGE0_URL:
    raise Exception("JUDGE0_PUBLIC_URL is missing in .env")

# =====================================
# FASTAPI
# =====================================

app = FastAPI()

# =====================================
# REQUEST MODEL
# =====================================

class CodeRequest(BaseModel):
    code: str
    context: str = ""

# =====================================
# GRAPH STATE
# =====================================

class GraphState(TypedDict):

    code: str

    original_code: str

    context: str

    language: str

    understanding: str

    raw_testcase_response: str

    testcases: List[Dict[str, Any]]

    judge0_results: List[Dict[str, Any]]

    validated_results: List[Dict[str, Any]]

    score: int

    improved_code: str

    explanation: str

# =====================================
# LANGUAGE MAP
# =====================================

LANGUAGE_MAP = {
    "assembly": 45,
    "bash": 46,
    "basic": 47,

    "c": 50,
    "cpp": 54,
    "c++": 54,

    "csharp": 51,
    "c#": 51,

    "clojure": 86,
    "cobol": 77,
    "common_lisp": 55,
    "d": 56,
    "elixir": 57,
    "erlang": 58,
    "fsharp": 87,
    "f#": 87,
    "fortran": 59,
    "go": 60,
    "groovy": 88,
    "haskell": 61,

    "java": 62,
    "javascript": 63,
    "js": 63,

    "kotlin": 78,
    "lua": 64,
    "objective_c": 79,
    "ocaml": 65,
    "octave": 66,
    "pascal": 67,
    "perl": 85,
    "php": 68,
    "prolog": 69,

    "python": 71,
    "python3": 71,
    "python2": 70,

    "r": 80,
    "ruby": 72,
    "rust": 73,
    "scala": 81,
    "sql": 82,
    "swift": 83,

    "typescript": 74,
    "ts": 74,

    "visual_basic": 84,
    "vb": 84
}

# =====================================
# PROMPTS
# =====================================

LANGUAGE_DETECTION_PROMPT = """
You are a programming language detection agent.

Detect the programming language of the following code.

Return ONLY one of these exact values:

assembly
bash
basic
c
cpp
csharp
clojure
cobol
common_lisp
d
elixir
erlang
fsharp
fortran
go
groovy
haskell
java
javascript
kotlin
lua
objective_c
ocaml
octave
pascal
perl
php
prolog
python
r
ruby
rust
scala
sql
swift
typescript
visual_basic

Do not explain anything.

CODE:
{code}
"""

UNDERSTANDING_PROMPT = """
You are an expert competitive programming and backend code analyst.

Analyze the main code and the additional dependent context files.

Your job:
1. Understand what the main code is trying to do.
2. Use the dependent context files to infer missing behavior.
3. Identify input format.
4. Identify output format.
5. Identify important edge cases.
6. If this is backend-style code, convert the behavior into stdin/stdout-testable logic where possible.
7. Clearly mention assumptions if the code depends on frameworks, databases, middleware, or external packages.

MAIN CODE:
{code}

DEPENDENT CONTEXT FILES:
{context}
"""

TESTCASE_PROMPT = """
You are an expert testcase generator.

Based on the following understanding and dependent context:

{understanding}

Generate:
1. 6 testcases
2. Include normal + edge cases
3. Each testcase must contain:
   - stdin
   - expected_stdout
4. The testcases must match the inferred stdin/stdout behavior.
5. Do not generate invalid runtime-crash cases unless the problem clearly expects handling them.
6. expected_stdout must be exactly what the correct program should print.
7. Use the dependent context files to generate more accurate testcases.

Return STRICT JSON ONLY.

Example:

[
  {{
    "stdin": "test@example.com password123",
    "expected_stdout": "Login successful"
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
You are an expert competitive programming and backend code improvement agent.

The user's main code was executed against generated testcases using Judge0.

Your job:
1. Read the problem understanding.
2. Read the original main code.
3. Read the dependent context files.
4. Read all generated testcases.
5. Read Judge0 execution results.
6. Read validation results showing PASS/FAIL.
7. Suggest one better corrected version of the MAIN CODE only.
8. Preserve the same input/output format.
9. Return ONLY the full corrected main code.
10. Do not explain anything.
11. Do not use markdown.

Important:
- Do not assume the suggested code will be re-tested.
- Your output must be the best final suggested main code based on the available results.
- If the original code already passes all testcases, still return the original main code unchanged.
- Keep the suggested code in the same programming language as the original code.
- Use dependent context files only for understanding behavior. Do not merge all files unless required.

Detected Language:
{language}

Problem Understanding:
{understanding}

Original Main Code:
{code}

Dependent Context Files:
{context}

Generated Testcases:
{testcases}

Judge0 Results:
{judge0_results}

Validated Results:
{validated_results}
"""

EXPLANATION_PROMPT = """
You are a code review explanation agent.

The user's original code was tested using generated testcases.

Your job:
1. Explain what made the testcase(s) fail.
2. Explain the likely bug or missing logic in the original code.
3. Explain how the improved code fixes the issue.
4. Keep the explanation simple and beginner-friendly.
5. Do not be too long.
6. Use bullet points.

Important:
- If every testcase passed, return exactly:
The code is safe and secured based on the generated testcases.

Problem Understanding:
{understanding}

Detected Language:
{language}

Original Code:
{original_code}

Improved Code:
{improved_code}

Generated Testcases:
{testcases}

Validated Results:
{validated_results}

Score:
{score}/{total}
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


def normalize_language(language: str):

    language = language.strip().lower()

    language = language.replace(" ", "_")
    language = language.replace("-", "_")

    aliases = {
        "c++": "cpp",
        "cpp17": "cpp",
        "cpp14": "cpp",
        "cpp20": "cpp",

        "c#": "csharp",
        "cs": "csharp",

        "f#": "fsharp",

        "js": "javascript",
        "node": "javascript",
        "nodejs": "javascript",
        "node.js": "javascript",

        "py": "python",
        "python3": "python",

        "ts": "typescript",

        "vb": "visual_basic",
        "vb.net": "visual_basic",
        "visual_basic.net": "visual_basic"
    }

    return aliases.get(language, language)


def ai_detect_language(code: str):

    prompt = LANGUAGE_DETECTION_PROMPT.format(
        code=code
    )

    language = invoke_llm(prompt)

    language = normalize_language(language)

    if language not in LANGUAGE_MAP:

        raise Exception(
            f"Unsupported or unknown language detected by AI: {language}"
        )

    return language


def detect_language(code: str):

    lowered_code = code.lower()
    stripped_code = code.strip()
    stripped_lowered_code = lowered_code.strip()

    # Java
    if (
        "public class" in code
        or "public static void main" in code
        or "system.out.println" in lowered_code
    ):
        return "java"

    # C++
    if (
        "#include <bits/stdc++.h>" in code
        or "using namespace std" in code
        or "std::" in code
        or "cout <<" in code
        or "cin >>" in code
    ):
        return "cpp"

    # C
    if (
        "#include <stdio.h>" in code
        or "printf(" in code
        or "scanf(" in code
    ):
        return "c"

    # JavaScript / Node.js
    if (
        "console.log" in code
        or "require(" in code
        or "process.stdin" in code
        or "fs.readfilesync" in lowered_code
        or "const fs" in lowered_code
        or "let " in code
        or "const " in code
    ):
        return "javascript"

    # TypeScript
    if (
        ": number" in code
        or ": string" in code
        or ": boolean" in code
        or "interface " in code
        or "type " in code
    ):
        return "typescript"

    # Python
    if (
        "def " in code
        or "print(" in code
        or "input(" in code
        or "import sys" in code
        or "from " in code
    ):
        return "python"

    # Go
    if (
        "package main" in code
        and "func main()" in code
    ):
        return "go"

    # Rust
    if (
        "fn main()" in code
        or "println!" in code
    ):
        return "rust"

    # PHP
    if "<?php" in code:
        return "php"

    # Ruby
    if (
        "puts " in code
        or "gets" in code
    ):
        return "ruby"

    # Swift
    if (
        "import foundation" in lowered_code
        or ("print(" in code and "let " in code)
    ):
        return "swift"

    # Kotlin
    if (
        "fun main" in code
        or ("println(" in code and "val " in code)
    ):
        return "kotlin"

    # SQL
    if (
        stripped_lowered_code.startswith("select ")
        or stripped_lowered_code.startswith("insert ")
        or stripped_lowered_code.startswith("update ")
        or stripped_lowered_code.startswith("delete ")
        or stripped_lowered_code.startswith("create table")
    ):
        return "sql"

    # Bash
    if (
        stripped_code.startswith("#!/bin/bash")
        or stripped_code.startswith("#!/usr/bin/env bash")
        or "echo " in code
    ):
        return "bash"

    # Fallback to AI
    return ai_detect_language(code)


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


def clean_code_response(text: str):

    text = text.strip()

    text = re.sub(
        r"^```[a-zA-Z0-9_+#.-]*",
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
        code=state["code"],
        context=state.get("context", "")
    )

    understanding = invoke_llm(prompt)

    return {
        "understanding": understanding
    }


def language_agent(state: GraphState):

    language = detect_language(
        state["code"]
    )

    return {
        "language": language
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


def judge0_agent(state: GraphState):

    code = state["code"]

    language = state["language"]

    if language not in LANGUAGE_MAP:

        raise Exception(
            f"Unsupported language: {language}"
        )

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
            f"No Judge0 tokens received. Response: {data}"
        )

    # =====================================
    # POLLING
    # =====================================

    completed = False

    final_results = None

    for _ in range(30):

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

        if all_done and submissions_data:

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

            except Exception:

                stdout = result["stdout"]

        stderr = ""

        if result.get("stderr"):

            try:

                stderr = base64.b64decode(
                    result["stderr"]
                ).decode().strip()

            except Exception:

                stderr = result["stderr"]

        compile_output = ""

        if result.get("compile_output"):

            try:

                compile_output = base64.b64decode(
                    result["compile_output"]
                ).decode().strip()

            except Exception:

                compile_output = result["compile_output"]

        message = ""

        if result.get("message"):

            try:

                message = base64.b64decode(
                    result["message"]
                ).decode().strip()

            except Exception:

                message = result["message"]

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

            "message":
                message,

            "status":
                result.get("status", {}).get(
                    "description",
                    "Unknown"
                )
        })

    return {
        "judge0_results": results
    }


def validation_agent(state: GraphState):

    validated = []

    score = 0

    for tc in state["judge0_results"]:

        expected = tc["expected_output"].strip()

        actual = tc["actual_output"].strip()

        status = tc.get("status", "")

        stderr = tc.get("stderr", "")

        compile_output = tc.get("compile_output", "")

        if status != "Accepted" or stderr or compile_output:

            passed = False

        elif expected == actual:

            passed = True

        else:

            prompt = VALIDATION_PROMPT.format(
                expected=expected,
                actual=actual
            )

            result = invoke_llm(prompt)

            passed = result.strip().upper() == "PASS"

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


def improvement_agent(state: GraphState):

    prompt = IMPROVEMENT_PROMPT.format(
        language=state["language"],
        understanding=state["understanding"],
        code=state["original_code"],
        context=state.get("context", ""),
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


def explanation_agent(state: GraphState):

    score = state["score"]
    total = len(state["validated_results"])

    if score == total:

        return {
            "explanation": "The code is safe and secured based on the generated testcases."
        }

    prompt = EXPLANATION_PROMPT.format(
        understanding=state["understanding"],
        language=state["language"],
        original_code=state["original_code"],
        improved_code=state["improved_code"],
        testcases=json.dumps(
            state["testcases"],
            indent=2
        ),
        validated_results=json.dumps(
            state["validated_results"],
            indent=2
        ),
        score=score,
        total=total
    )

    explanation = invoke_llm(prompt)

    return {
        "explanation": explanation.strip()
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
        "language_agent",
        language_agent
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

    graph.add_node(
        "explanation_agent",
        explanation_agent
    )

    graph.set_entry_point(
        "context_agent"
    )

    graph.add_edge(
        "context_agent",
        "language_agent"
    )

    graph.add_edge(
        "language_agent",
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
        "explanation_agent"
    )

    graph.add_edge(
        "explanation_agent",
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
        "code": req.code,
        "original_code": req.code,
        "context": req.context,
        "improved_code": req.code,
        "explanation": ""
    })

    return {

        "success": True,

        "detected_language":
            result["language"],

        "language_id":
            LANGUAGE_MAP[result["language"]],

        "score":
            result["score"],

        "total_testcases":
            len(result["validated_results"]),

        "original_code":
            result["original_code"],

        "context":
            result.get("context", ""),

        "improved_code":
            result.get(
                "improved_code",
                result["original_code"]
            ),

        "explanation":
            result.get(
                "explanation",
                ""
            ),

        "results":
            result["validated_results"]
    }