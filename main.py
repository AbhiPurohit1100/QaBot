from fastapi import FastAPI
from fastapi.responses import StreamingResponse
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

# =====================================
# TPM THROTTLE CONFIG
# =====================================

INTER_LLM_DELAY = 5  # seconds between LLM calls to spread token usage
MAX_RETRIES = 5      # max retries on rate limit (429)

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

    merged_code: str

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
1. 4 testcases
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

BATCH_VALIDATION_PROMPT = """
You are a testcase validation agent.

You will receive multiple expected/actual output pairs.
For each pair, determine if they are logically equivalent.

Return ONLY a JSON array of results in the same order.
Each result must be exactly "PASS" or "FAIL".

Example response:
["PASS", "FAIL", "PASS"]

Pairs to validate:
{pairs}
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

MERGE_PROMPT = """
You are a code merging agent.

You are given a MAIN CODE file and one or more DEPENDENCY FILES.
Your job is to produce a SINGLE self-contained executable file that combines all of them.

Rules:
1. Inline all dependency code into the main code so it runs as one file.
2. Remove or replace import/require/include statements that reference the dependency files.
3. Place dependency code (functions, classes, constants) BEFORE the main code that uses them.
4. Preserve the exact stdin/stdout behavior of the main code.
5. Do not add any extra output, comments, or explanations.
6. Do not use markdown formatting.
7. Return ONLY the final merged executable code.
8. Keep the code in the same programming language.

Detected Language:
{language}

MAIN CODE:
{code}

DEPENDENCY FILES:
{context}
"""

# =====================================
# HELPERS
# =====================================

_last_llm_call_time = 0

def invoke_llm(prompt: str, max_tokens: int = 4096):
    """Call the LLM with automatic retry on rate limits and inter-call throttling."""
    global _last_llm_call_time

    # Inter-call delay to spread token usage across the TPM window
    elapsed = time.time() - _last_llm_call_time
    if elapsed < INTER_LLM_DELAY:
        wait_time = INTER_LLM_DELAY - elapsed
        print(f"[TPM] Throttling: waiting {wait_time:.1f}s before next LLM call")
        time.sleep(wait_time)

    for attempt in range(MAX_RETRIES):
        try:
            completion = client.chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.1,
                max_completion_tokens=max_tokens,
                top_p=1,
                reasoning_effort="medium",
                stream=False
            )

            _last_llm_call_time = time.time()
            return completion.choices[0].message.content.strip()

        except Exception as e:
            error_str = str(e).lower()
            if "rate_limit" in error_str or "429" in error_str or "rate limit" in error_str:
                wait = min(15 * (2 ** attempt), 90)
                print(f"[TPM] Rate limited (attempt {attempt + 1}/{MAX_RETRIES}). Waiting {wait}s...")
                time.sleep(wait)
            else:
                raise

    raise Exception("LLM rate limit exceeded after maximum retries")


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


def merge_agent(state: GraphState):

    context = state.get("context", "").strip()

    # If no dependency files, skip merge — just use the main code as-is
    if not context:

        return {
            "merged_code": state["code"]
        }

    prompt = MERGE_PROMPT.format(
        language=state["language"],
        code=state["code"],
        context=context
    )

    merged = invoke_llm(prompt)

    merged = clean_code_response(merged)

    return {
        "merged_code": merged
    }


def judge0_agent(state: GraphState):

    # Use merged code (main + dependencies) for execution
    code = state.get("merged_code") or state["code"]

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

    # Pre-classify: separate exact matches, errors, and mismatches
    pre_results = []  # (index, passed | None)
    mismatch_indices = []  # indices needing LLM validation
    mismatch_pairs = []    # pairs to send to LLM

    for idx, tc in enumerate(state["judge0_results"]):

        expected = tc["expected_output"].strip()
        actual = tc["actual_output"].strip()
        status = tc.get("status", "")
        stderr = tc.get("stderr", "")
        compile_output = tc.get("compile_output", "")

        if status != "Accepted" or stderr or compile_output:
            pre_results.append((idx, False))

        elif expected == actual:
            pre_results.append((idx, True))

        else:
            pre_results.append((idx, None))  # needs LLM
            mismatch_indices.append(idx)
            mismatch_pairs.append({
                "pair_number": len(mismatch_pairs) + 1,
                "expected": expected,
                "actual": actual
            })

    # Batch LLM call for all mismatches (single call instead of N calls)
    llm_results = {}

    if mismatch_pairs:

        if len(mismatch_pairs) == 1:
            # Single mismatch — use original simple prompt
            prompt = VALIDATION_PROMPT.format(
                expected=mismatch_pairs[0]["expected"],
                actual=mismatch_pairs[0]["actual"]
            )
            result = invoke_llm(prompt, max_tokens=128)
            llm_results[mismatch_indices[0]] = result.strip().upper() == "PASS"

        else:
            # Multiple mismatches — batch into one call
            pairs_text = json.dumps(mismatch_pairs, indent=2)
            prompt = BATCH_VALIDATION_PROMPT.format(pairs=pairs_text)
            result = invoke_llm(prompt, max_tokens=256)

            try:
                # Parse JSON array like ["PASS", "FAIL", "PASS"]
                match = re.search(r'\[.*\]', result, re.DOTALL)
                if match:
                    verdicts = json.loads(match.group())
                else:
                    verdicts = []

                for i, idx in enumerate(mismatch_indices):
                    if i < len(verdicts):
                        llm_results[idx] = verdicts[i].strip().upper() == "PASS"
                    else:
                        llm_results[idx] = False  # fallback to FAIL

            except Exception:
                # If parsing fails, fall back to all FAIL
                for idx in mismatch_indices:
                    llm_results[idx] = False

    # Assemble final results
    for idx, tc in enumerate(state["judge0_results"]):

        # Find the pre-classification
        _, pre_passed = pre_results[idx]

        if pre_passed is None:
            passed = llm_results.get(idx, False)
        else:
            passed = pre_passed

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

    # Trim judge0_results: only include full details for failing testcases
    trimmed_judge0 = []
    for idx, r in enumerate(state["judge0_results"]):
        validated = state["validated_results"][idx] if idx < len(state["validated_results"]) else {}
        if validated.get("passed", False):
            # For passing tests, only include stdin and status
            trimmed_judge0.append({
                "stdin": r.get("stdin", ""),
                "status": r.get("status", ""),
                "passed": True
            })
        else:
            trimmed_judge0.append(r)

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
            trimmed_judge0,
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
        "merge_agent",
        merge_agent
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
        "merge_agent"
    )

    graph.add_edge(
        "merge_agent",
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


# =====================================
# STREAMING ROUTE (SSE)
# =====================================

# Maps agent node names to frontend step keys
AGENT_TO_STEP = {
    "context_agent": "understanding",
    "language_agent": "language",
    "testcase_agent": "testcase",
    "parser_agent": "testcase",       # parser is part of testcase step
    "merge_agent": "merge",
    "judge0_agent": "judge0",
    "validation_agent": "validation",
    "improvement_agent": "improvement",
    "explanation_agent": "explanation"
}

@app.post("/generate-testcases-stream")
def generate_testcases_stream(req: CodeRequest):

    def event_stream():

        state = {
            "code": req.code,
            "original_code": req.code,
            "context": req.context,
            "improved_code": req.code,
            "explanation": ""
        }

        # Define the pipeline steps in order
        agents = [
            ("context_agent", context_agent),
            ("language_agent", language_agent),
            ("testcase_agent", testcase_agent),
            ("parser_agent", parser_agent),
            ("merge_agent", merge_agent),
            ("judge0_agent", judge0_agent),
            ("validation_agent", validation_agent),
            ("improvement_agent", improvement_agent),
            ("explanation_agent", explanation_agent),
        ]

        for agent_name, agent_fn in agents:

            step_key = AGENT_TO_STEP.get(agent_name, agent_name)

            # Send "running" event
            yield f"data: {json.dumps({'type': 'step_running', 'step': step_key})}\n\n"

            try:
                result = agent_fn(state)
                state.update(result)
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'step': step_key, 'message': str(e)})}\n\n"
                return

            # Send "completed" event
            yield f"data: {json.dumps({'type': 'step_complete', 'step': step_key})}\n\n"

        # Send final result
        final_result = {
            "type": "result",
            "success": True,
            "detected_language": state["language"],
            "language_id": LANGUAGE_MAP[state["language"]],
            "score": state["score"],
            "total_testcases": len(state["validated_results"]),
            "original_code": state["original_code"],
            "context": state.get("context", ""),
            "improved_code": state.get("improved_code", state["original_code"]),
            "explanation": state.get("explanation", ""),
            "results": state["validated_results"]
        }

        yield f"data: {json.dumps(final_result)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream"
    )